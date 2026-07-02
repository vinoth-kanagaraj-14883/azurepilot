"""
Correlation engine — merges Resource Health events and metric anomaly profiles
into unified Incident objects.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, Field

from analysis.anomaly import MetricAnomaly, ResourceRiskProfile
from ingestion.models import AzureResource, HealthEvent, HealthStatus, ResourceType


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


def _risk_to_severity(risk_score: float, health_status: HealthStatus) -> Severity:
    if health_status == HealthStatus.UNAVAILABLE or risk_score >= 85:
        return Severity.CRITICAL
    if health_status == HealthStatus.DEGRADED or risk_score >= 65:
        return Severity.HIGH
    if risk_score >= 40:
        return Severity.MEDIUM
    if risk_score >= 15:
        return Severity.LOW
    return Severity.NONE


class ContributingMetric(BaseModel):
    metric_name: str
    current_value: float
    baseline_mean: float
    z_score: float
    risk_contribution: float
    unit: str = ""


class Incident(BaseModel):
    """A correlated incident merging health + metric signals for one resource."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_id: str
    resource_name: str
    resource_type: ResourceType
    resource_group: str
    location: str

    # Risk & health
    risk_score: float                        # 0-100
    severity: Severity
    health_status: HealthStatus
    health_reason: str = ""
    is_platform_issue: bool = False

    # Signals
    contributing_metrics: list[ContributingMetric] = Field(default_factory=list)
    anomaly_count: int = 0

    # Time
    detected_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    health_event_time: datetime | None = None
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None

    # AI fields (populated later by the AI module)
    summary: str = ""
    root_cause_hypothesis: str = ""
    recommended_action: str = ""

    # Cost
    estimated_cost_impact_usd: float = 0.0
    cost_impact_description: str = ""


def correlate(
    resources: Sequence[AzureResource],
    health_events: Sequence[HealthEvent],
    risk_profiles: Sequence[ResourceRiskProfile],
    lookback_hours: int = 24,
) -> list[Incident]:
    """
    Correlate resource health events and metric risk profiles into incidents.

    All three lists are matched by resource ID.  An Incident is created for
    every resource that has either:
      - A non-AVAILABLE health status, OR
      - A risk_score >= 15 (LOW threshold)

    Resources that are fully healthy and have negligible metric risk are omitted.
    """
    # Build lookup dictionaries
    health_by_rid = {e.resource_id: e for e in health_events}
    profile_by_rid = {p.resource_id: p for p in risk_profiles}

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=lookback_hours)

    incidents: list[Incident] = []

    for resource in resources:
        health_event = health_by_rid.get(resource.id)
        risk_profile = profile_by_rid.get(resource.id)

        health_status = (
            health_event.status if health_event else HealthStatus.UNKNOWN
        )
        health_reason = (
            health_event.reason if health_event else ""
        )
        is_platform = (
            health_event.is_platform_issue if health_event else False
        )
        health_time = (
            health_event.occurred_time if health_event else None
        )

        risk_score = risk_profile.risk_score if risk_profile else 0.0
        anomalies: list[MetricAnomaly] = risk_profile.anomalies if risk_profile else []

        severity = _risk_to_severity(risk_score, health_status)

        # Skip fully healthy, no-risk resources
        if severity == Severity.NONE and health_status == HealthStatus.AVAILABLE:
            continue

        contributing = [
            ContributingMetric(
                metric_name=a.metric_name,
                current_value=round(a.current_value, 4),
                baseline_mean=round(a.baseline_mean, 4),
                z_score=round(a.z_score, 3),
                risk_contribution=round(a.risk_contribution, 1),
                unit=a.unit,
            )
            for a in anomalies
            if a.risk_contribution > 5.0  # only meaningful contributors
        ]

        incident = Incident(
            resource_id=resource.id,
            resource_name=resource.name,
            resource_type=resource.resource_type,
            resource_group=resource.resource_group,
            location=resource.location,
            risk_score=risk_score,
            severity=severity,
            health_status=health_status,
            health_reason=health_reason,
            is_platform_issue=is_platform,
            contributing_metrics=contributing,
            anomaly_count=len(anomalies),
            detected_at=now,
            health_event_time=health_time,
            time_window_start=window_start,
            time_window_end=now,
        )
        incidents.append(incident)

    # Sort by risk score descending
    incidents.sort(key=lambda i: i.risk_score, reverse=True)
    return incidents
