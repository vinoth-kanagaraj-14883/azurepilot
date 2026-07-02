"""
Baseline and anomaly scoring.

Uses a simple z-score approach:
  1. Compute a rolling baseline (mean + stddev) for each metric.
  2. Compare the most recent window against the baseline.
  3. Map to a 0-100 risk score, taking into account directionality
     (high CPU/latency/errors are bad; high memory available is good).
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence

from ingestion.models import MetricSeries

# --- Metric directionality ---
# "high" means high values are risky; "low" means low values are risky.
METRIC_RISK_DIRECTION: dict[str, str] = {
    # VM
    "Percentage CPU": "high",
    "Available Memory Bytes": "low",
    "Network In Total": "high",
    "Network Out Total": "high",
    "Disk Read Bytes": "high",
    "Disk Write Bytes": "high",
    # App Service
    "CpuTime": "high",
    "Http5xx": "high",
    "HttpQueueLength": "high",
    "AverageResponseTime": "high",
    "Requests": "high",
    "MemoryWorkingSet": "high",
    # Storage
    "Availability": "low",          # low availability is bad
    "Transactions": "high",
    "SuccessE2ELatency": "high",
    "Ingress": "high",
    "Egress": "high",
}

# Metric thresholds: above/below these baselines we consider it elevated risk
# These complement z-score by anchoring absolute thresholds
METRIC_THRESHOLDS: dict[str, dict[str, float]] = {
    "Percentage CPU": {"warning": 70.0, "critical": 90.0},
    "Http5xx": {"warning": 10.0, "critical": 50.0},
    "HttpQueueLength": {"warning": 20.0, "critical": 50.0},
    "AverageResponseTime": {"warning": 500.0, "critical": 2000.0},  # ms
    "Availability": {"warning": 99.0, "critical": 95.0},            # low is bad
    "SuccessE2ELatency": {"warning": 100.0, "critical": 500.0},     # ms
}


@dataclass
class MetricAnomaly:
    """Represents an anomaly detected in a single metric."""

    metric_name: str
    current_value: float
    baseline_mean: float
    baseline_stddev: float
    z_score: float
    risk_contribution: float  # 0-100 contribution to overall risk
    direction: str            # "high" or "low"
    unit: str = ""


@dataclass
class ResourceRiskProfile:
    """Aggregated risk profile for a single resource."""

    resource_id: str
    risk_score: float          # 0-100
    anomalies: list[MetricAnomaly] = field(default_factory=list)
    metric_count: int = 0


def compute_baseline(series: MetricSeries, baseline_fraction: float = 0.75) -> tuple[float, float]:
    """
    Compute rolling baseline mean and stddev from the first fraction of data.

    Args:
        series: Metric time series
        baseline_fraction: Fraction of data to use as baseline period (0-1)

    Returns:
        (mean, stddev) tuple
    """
    values = [dp.value for dp in series.data_points]
    if not values:
        return 0.0, 0.0

    cutoff = max(1, int(len(values) * baseline_fraction))
    baseline_values = values[:cutoff]

    mean = statistics.mean(baseline_values)
    stddev = statistics.stdev(baseline_values) if len(baseline_values) > 1 else 0.0
    return mean, stddev


def compute_z_score(current: float, mean: float, stddev: float) -> float:
    """Compute z-score. Returns signed relative deviation if stddev is near zero."""
    if stddev < 1e-9:
        # No variance in baseline; use signed relative deviation
        if mean > 1e-9:
            return (current - mean) / mean
        return 0.0
    return (current - mean) / stddev


def z_score_to_risk(z: float, direction: str) -> float:
    """
    Convert a z-score + direction to a 0-100 risk contribution.

    'high' direction: positive z means elevated risk.
    'low' direction: negative z means elevated risk (e.g. low availability).
    """
    if direction == "high":
        effective_z = z
    else:
        effective_z = -z

    # Sigmoid-like mapping: z=2 -> ~70%, z=3 -> ~90%, z=4 -> ~98%
    if effective_z <= 0:
        return 0.0
    risk = 100.0 * (1.0 - 1.0 / (1.0 + math.exp(effective_z - 1.5)))
    return min(100.0, risk)


def threshold_risk(metric_name: str, value: float, direction: str) -> float:
    """Apply hard threshold rules for well-known metrics."""
    thresholds = METRIC_THRESHOLDS.get(metric_name)
    if not thresholds:
        return 0.0

    warning = thresholds["warning"]
    critical = thresholds["critical"]

    if direction == "high":
        if value >= critical:
            return 90.0
        if value >= warning:
            return 60.0
    else:  # low direction: low values are bad
        if value <= critical:
            return 90.0
        if value <= warning:
            return 60.0
    return 0.0


def analyze_metric_series(series: MetricSeries) -> MetricAnomaly | None:
    """
    Compute anomaly score for a single metric series.

    Returns None if there is insufficient data.
    """
    if len(series.data_points) < 4:
        return None

    mean, stddev = compute_baseline(series)

    # Current value = average of the last 10% of data points
    values = [dp.value for dp in series.data_points]
    recent_n = max(1, len(values) // 10)
    current = statistics.mean(values[-recent_n:])

    z = compute_z_score(current, mean, stddev)
    direction = METRIC_RISK_DIRECTION.get(series.metric_name, "high")
    z_risk = z_score_to_risk(z, direction)
    t_risk = threshold_risk(series.metric_name, current, direction)

    # Take the maximum of z-score and threshold risk
    risk_contribution = max(z_risk, t_risk)

    unit = series.data_points[0].unit if series.data_points else ""
    return MetricAnomaly(
        metric_name=series.metric_name,
        current_value=current,
        baseline_mean=mean,
        baseline_stddev=stddev,
        z_score=z,
        risk_contribution=risk_contribution,
        direction=direction,
        unit=unit,
    )


def compute_resource_risk(
    resource_id: str, metric_series_list: Sequence[MetricSeries]
) -> ResourceRiskProfile:
    """
    Compute an overall 0-100 risk score for a resource given all its metric series.

    The aggregate score is a weighted combination:
      - Max anomaly risk (60% weight) — captures the worst single signal
      - Mean anomaly risk (40% weight) — captures broad degradation
    """
    anomalies: list[MetricAnomaly] = []
    for series in metric_series_list:
        anomaly = analyze_metric_series(series)
        if anomaly:
            anomalies.append(anomaly)

    if not anomalies:
        return ResourceRiskProfile(resource_id=resource_id, risk_score=0.0)

    contributions = [a.risk_contribution for a in anomalies]
    max_risk = max(contributions)
    mean_risk = statistics.mean(contributions)
    aggregate = 0.60 * max_risk + 0.40 * mean_risk

    return ResourceRiskProfile(
        resource_id=resource_id,
        risk_score=round(min(100.0, aggregate), 1),
        anomalies=sorted(anomalies, key=lambda a: a.risk_contribution, reverse=True),
        metric_count=len(anomalies),
    )
