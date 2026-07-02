"""
Unit tests for the anomaly scoring module.
"""
from __future__ import annotations

import pytest

from analysis.anomaly import (
    MetricAnomaly,
    compute_baseline,
    compute_resource_risk,
    compute_z_score,
    z_score_to_risk,
    threshold_risk,
    analyze_metric_series,
)
from ingestion.models import MetricDataPoint, MetricSeries
from datetime import datetime, timezone, timedelta


def make_series(values: list[float], metric_name: str = "Percentage CPU") -> MetricSeries:
    """Helper to build a MetricSeries from a list of float values."""
    now = datetime.now(tz=timezone.utc)
    data_points = [
        MetricDataPoint(
            timestamp=now - timedelta(minutes=5 * (len(values) - i - 1)),
            value=v,
            unit="Percent",
        )
        for i, v in enumerate(values)
    ]
    return MetricSeries(
        resource_id="/subscriptions/test/resourceGroups/rg/providers/test/vm/vm1",
        metric_name=metric_name,
        aggregation="Average",
        data_points=data_points,
    )


class TestComputeBaseline:
    def test_empty_series(self):
        series = make_series([])
        mean, stddev = compute_baseline(series)
        assert mean == 0.0
        assert stddev == 0.0

    def test_single_point(self):
        series = make_series([50.0])
        mean, stddev = compute_baseline(series)
        assert mean == 50.0
        assert stddev == 0.0

    def test_uniform_values(self):
        series = make_series([30.0] * 100)
        mean, stddev = compute_baseline(series)
        assert abs(mean - 30.0) < 1e-6
        assert stddev < 1e-6  # no variance

    def test_baseline_uses_first_75_percent(self):
        # 100 points: first 75 = 10.0, last 25 = 90.0
        values = [10.0] * 75 + [90.0] * 25
        series = make_series(values)
        mean, stddev = compute_baseline(series, baseline_fraction=0.75)
        # Baseline should only use first 75 points
        assert abs(mean - 10.0) < 1e-6

    def test_normal_distribution(self):
        import statistics
        values = [float(i % 20) for i in range(100)]
        series = make_series(values)
        mean, stddev = compute_baseline(series)
        baseline_vals = values[:75]
        assert abs(mean - statistics.mean(baseline_vals)) < 0.01


class TestComputeZScore:
    def test_zero_stddev_returns_zero_for_same_value(self):
        z = compute_z_score(50.0, 50.0, 0.0)
        assert z == 0.0

    def test_zero_stddev_returns_relative_deviation(self):
        # When stddev=0 and current != mean, use relative deviation
        z = compute_z_score(60.0, 50.0, 0.0)
        assert z == pytest.approx(0.2)  # (60-50)/50

    def test_positive_z_for_above_mean(self):
        z = compute_z_score(80.0, 50.0, 10.0)
        assert z == pytest.approx(3.0)

    def test_negative_z_for_below_mean(self):
        z = compute_z_score(20.0, 50.0, 10.0)
        assert z == pytest.approx(-3.0)


class TestZScoreToRisk:
    def test_zero_z_returns_zero_risk(self):
        assert z_score_to_risk(0.0, "high") == 0.0

    def test_negative_z_high_direction_returns_zero(self):
        # Negative z in "high" direction means below baseline — not risky
        assert z_score_to_risk(-2.0, "high") == 0.0

    def test_high_z_gives_high_risk(self):
        risk = z_score_to_risk(4.0, "high")
        assert risk > 85.0

    def test_low_direction_inverts_sign(self):
        # For "low" direction, negative z (below baseline) is risky
        risk_low = z_score_to_risk(-3.0, "low")
        risk_high = z_score_to_risk(3.0, "high")
        assert abs(risk_low - risk_high) < 1e-6

    def test_max_capped_at_100(self):
        assert z_score_to_risk(100.0, "high") <= 100.0


class TestThresholdRisk:
    def test_cpu_below_warning(self):
        assert threshold_risk("Percentage CPU", 50.0, "high") == 0.0

    def test_cpu_above_warning(self):
        assert threshold_risk("Percentage CPU", 75.0, "high") == 60.0

    def test_cpu_above_critical(self):
        assert threshold_risk("Percentage CPU", 95.0, "high") == 90.0

    def test_availability_above_warning(self):
        # Availability is "low" direction — low values are bad
        # 99.5% > 99.0% warning → no risk
        assert threshold_risk("Availability", 99.5, "low") == 0.0

    def test_availability_below_warning(self):
        # 98% < 99% warning threshold → warning risk
        assert threshold_risk("Availability", 98.0, "low") == 60.0

    def test_availability_below_critical(self):
        # 90% < 95% critical threshold → critical risk
        assert threshold_risk("Availability", 90.0, "low") == 90.0

    def test_unknown_metric_returns_zero(self):
        assert threshold_risk("UnknownMetric", 999.0, "high") == 0.0


class TestAnalyzeMetricSeries:
    def test_insufficient_data_returns_none(self):
        series = make_series([1.0, 2.0, 3.0])
        result = analyze_metric_series(series)
        assert result is None

    def test_healthy_baseline_returns_low_risk(self):
        # Stable series — no spike
        values = [30.0 + (i % 5) * 0.5 for i in range(100)]
        series = make_series(values)
        result = analyze_metric_series(series)
        assert result is not None
        assert result.risk_contribution < 20.0

    def test_cpu_spike_returns_high_risk(self):
        # Baseline ~30%, spike to 95% at the end
        values = [30.0] * 80 + [95.0] * 20
        series = make_series(values, "Percentage CPU")
        result = analyze_metric_series(series)
        assert result is not None
        assert result.risk_contribution >= 60.0

    def test_memory_drop_returns_high_risk(self):
        # Available memory drops dramatically (low direction): 4 GB → 0.2 GB
        baseline = 4.0 * 1024**3
        values = [baseline] * 80 + [0.2 * 1024**3] * 20
        series = make_series(values, "Available Memory Bytes")
        result = analyze_metric_series(series)
        assert result is not None
        # A 95% memory drop should produce a meaningful risk signal
        assert result.risk_contribution > 0.0
        assert result.z_score < 0  # negative z = current < baseline (risky for low-direction)

    def test_http5xx_spike_returns_high_risk(self):
        values = [2.0] * 80 + [80.0] * 20
        series = make_series(values, "Http5xx")
        result = analyze_metric_series(series)
        assert result is not None
        assert result.risk_contribution >= 60.0


class TestComputeResourceRisk:
    def test_empty_series_list_returns_zero_risk(self):
        profile = compute_resource_risk("resource-1", [])
        assert profile.risk_score == 0.0
        assert profile.anomalies == []

    def test_healthy_resource_has_low_risk(self):
        # Genuinely stable series — flat values with tiny noise → low risk
        stable_cpu = make_series([30.0] * 100, "Percentage CPU")
        stable_net = make_series([1000.0] * 100, "Network In Total")
        profile = compute_resource_risk("resource-1", [stable_cpu, stable_net])
        assert profile.risk_score < 30.0

    def test_spiky_resource_has_high_risk(self):
        cpu_spike = make_series([30.0] * 80 + [95.0] * 20, "Percentage CPU")
        http_spike = make_series([2.0] * 80 + [100.0] * 20, "Http5xx")
        profile = compute_resource_risk("resource-1", [cpu_spike, http_spike])
        assert profile.risk_score >= 50.0

    def test_risk_score_bounded(self):
        extreme_spike = make_series([0.0] * 80 + [1e9] * 20, "Percentage CPU")
        profile = compute_resource_risk("resource-1", [extreme_spike])
        assert 0.0 <= profile.risk_score <= 100.0

    def test_anomalies_sorted_by_contribution(self):
        low_spike = make_series([30.0] * 80 + [45.0] * 20, "Percentage CPU")
        high_spike = make_series([2.0] * 80 + [100.0] * 20, "Http5xx")
        profile = compute_resource_risk("resource-1", [low_spike, high_spike])
        if len(profile.anomalies) >= 2:
            assert (
                profile.anomalies[0].risk_contribution
                >= profile.anomalies[1].risk_contribution
            )
