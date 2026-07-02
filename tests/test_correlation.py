"""
Unit tests for the correlation engine.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from analysis.anomaly import ResourceRiskProfile, MetricAnomaly
from analysis.correlation import (
    Incident,
    Severity,
    ContributingMetric,
    correlate,
    _risk_to_severity,
)
from ingestion.models import AzureResource, HealthEvent, HealthStatus, ResourceType


def make_resource(
    name: str = "test-vm",
    resource_type: ResourceType = ResourceType.VIRTUAL_MACHINE,
    rg: str = "rg-test",
) -> AzureResource:
    sub = "00000000-test-0000-0000-000000000000"
    rid = f"/subscriptions/{sub}/resourceGroups/{rg}/providers/{resource_type.value}/{name}"
    return AzureResource(
        id=rid,
        name=name,
        resource_type=resource_type,
        resource_group=rg,
        location="eastus",
        subscription_id=sub,
    )


def make_health_event(
    resource_id: str,
    status: HealthStatus = HealthStatus.AVAILABLE,
    reason: str = "",
    is_platform: bool = False,
) -> HealthEvent:
    now = datetime.now(tz=timezone.utc)
    return HealthEvent(
        resource_id=resource_id,
        status=status,
        reason=reason,
        occurred_time=now - timedelta(minutes=30),
        reported_time=now - timedelta(minutes=28),
        is_platform_issue=is_platform,
    )


def make_risk_profile(
    resource_id: str,
    risk_score: float = 0.0,
    metric_name: str = "Percentage CPU",
    risk_contribution: float = 0.0,
) -> ResourceRiskProfile:
    anomalies = []
    if risk_contribution > 0:
        anomalies.append(
            MetricAnomaly(
                metric_name=metric_name,
                current_value=90.0,
                baseline_mean=30.0,
                baseline_stddev=5.0,
                z_score=3.0,
                risk_contribution=risk_contribution,
                direction="high",
            )
        )
    return ResourceRiskProfile(
        resource_id=resource_id,
        risk_score=risk_score,
        anomalies=anomalies,
        metric_count=len(anomalies),
    )


class TestRiskToSeverity:
    def test_unavailable_health_always_critical(self):
        assert _risk_to_severity(0.0, HealthStatus.UNAVAILABLE) == Severity.CRITICAL

    def test_high_risk_score_critical(self):
        assert _risk_to_severity(90.0, HealthStatus.AVAILABLE) == Severity.CRITICAL

    def test_degraded_health_at_least_high(self):
        sev = _risk_to_severity(0.0, HealthStatus.DEGRADED)
        assert sev in (Severity.HIGH, Severity.CRITICAL)

    def test_low_risk_available_resource(self):
        assert _risk_to_severity(5.0, HealthStatus.AVAILABLE) == Severity.NONE

    def test_medium_risk(self):
        assert _risk_to_severity(45.0, HealthStatus.AVAILABLE) == Severity.MEDIUM

    def test_low_severity(self):
        assert _risk_to_severity(20.0, HealthStatus.AVAILABLE) == Severity.LOW


class TestCorrelate:
    def test_healthy_resource_excluded(self):
        resource = make_resource("vm-healthy")
        health = make_health_event(resource.id, HealthStatus.AVAILABLE)
        profile = make_risk_profile(resource.id, risk_score=5.0)

        incidents = correlate([resource], [health], [profile])
        assert incidents == []  # risk=5, severity=NONE, available → excluded

    def test_unhealthy_resource_included(self):
        resource = make_resource("vm-sick")
        health = make_health_event(resource.id, HealthStatus.UNAVAILABLE, "Platform issue")
        profile = make_risk_profile(resource.id, risk_score=90.0, risk_contribution=90.0)

        incidents = correlate([resource], [health], [profile])
        assert len(incidents) == 1
        inc = incidents[0]
        assert inc.resource_name == "vm-sick"
        assert inc.severity == Severity.CRITICAL
        assert inc.health_status == HealthStatus.UNAVAILABLE
        assert inc.is_platform_issue is False  # make_health_event default

    def test_platform_issue_flag_propagated(self):
        resource = make_resource("storage-degraded", ResourceType.STORAGE_ACCOUNT)
        health = make_health_event(
            resource.id, HealthStatus.UNAVAILABLE, "Azure storage outage", is_platform=True
        )
        profile = make_risk_profile(resource.id, risk_score=80.0, risk_contribution=80.0)

        incidents = correlate([resource], [health], [profile])
        assert incidents[0].is_platform_issue is True

    def test_sorted_by_risk_score_descending(self):
        r1 = make_resource("vm-low")
        r2 = make_resource("vm-high")
        h1 = make_health_event(r1.id, HealthStatus.DEGRADED)
        h2 = make_health_event(r2.id, HealthStatus.DEGRADED)
        p1 = make_risk_profile(r1.id, risk_score=30.0, risk_contribution=30.0)
        p2 = make_risk_profile(r2.id, risk_score=85.0, risk_contribution=85.0)

        incidents = correlate([r1, r2], [h1, h2], [p1, p2])
        assert len(incidents) == 2
        assert incidents[0].risk_score >= incidents[1].risk_score

    def test_missing_health_event_uses_unknown(self):
        resource = make_resource("vm-no-health")
        profile = make_risk_profile(resource.id, risk_score=50.0, risk_contribution=50.0)

        # No health event provided
        incidents = correlate([resource], [], [profile])
        assert len(incidents) == 1
        assert incidents[0].health_status == HealthStatus.UNKNOWN

    def test_missing_risk_profile_uses_zero_score(self):
        resource = make_resource("vm-no-metrics")
        health = make_health_event(resource.id, HealthStatus.DEGRADED)

        # No risk profile
        incidents = correlate([resource], [health], [])
        assert len(incidents) == 1
        assert incidents[0].risk_score == 0.0
        assert incidents[0].severity == Severity.HIGH  # degraded health overrides

    def test_contributing_metrics_filtered_by_significance(self):
        resource = make_resource("vm-test")
        health = make_health_event(resource.id, HealthStatus.DEGRADED)

        # Profile with one significant and one insignificant anomaly
        profile = ResourceRiskProfile(
            resource_id=resource.id,
            risk_score=60.0,
            anomalies=[
                MetricAnomaly(
                    metric_name="Percentage CPU",
                    current_value=90.0,
                    baseline_mean=30.0,
                    baseline_stddev=5.0,
                    z_score=3.0,
                    risk_contribution=80.0,  # significant
                    direction="high",
                ),
                MetricAnomaly(
                    metric_name="Network In Total",
                    current_value=1100.0,
                    baseline_mean=1000.0,
                    baseline_stddev=50.0,
                    z_score=2.0,
                    risk_contribution=2.0,  # below 5% threshold
                    direction="high",
                ),
            ],
        )

        incidents = correlate([resource], [health], [profile])
        assert len(incidents) == 1
        # Only the significant metric should be in contributing_metrics
        metric_names = [m.metric_name for m in incidents[0].contributing_metrics]
        assert "Percentage CPU" in metric_names
        assert "Network In Total" not in metric_names

    def test_multiple_resource_types(self):
        vm = make_resource("vm-1", ResourceType.VIRTUAL_MACHINE)
        app = make_resource("app-1", ResourceType.APP_SERVICE, "rg-app")
        storage = make_resource("storage-1", ResourceType.STORAGE_ACCOUNT, "rg-storage")

        resources = [vm, app, storage]
        health_events = [
            make_health_event(vm.id, HealthStatus.DEGRADED),
            make_health_event(app.id, HealthStatus.AVAILABLE),
            make_health_event(storage.id, HealthStatus.UNAVAILABLE),
        ]
        profiles = [
            make_risk_profile(vm.id, risk_score=55.0, risk_contribution=55.0),
            make_risk_profile(app.id, risk_score=8.0),  # healthy, below NONE threshold
            make_risk_profile(storage.id, risk_score=88.0, risk_contribution=88.0),
        ]

        incidents = correlate(resources, health_events, profiles)
        resource_names = [i.resource_name for i in incidents]
        assert "vm-1" in resource_names
        assert "storage-1" in resource_names
        # app-1 has risk=8 and status=Available → severity=NONE → excluded
        assert "app-1" not in resource_names
