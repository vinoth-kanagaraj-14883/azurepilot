"""
Pydantic response schemas for the AzurePilot REST API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ResourceResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    resource_group: str
    location: str
    risk_score: float
    health_status: str
    severity: str


class ContributingMetricResponse(BaseModel):
    metric_name: str
    current_value: float
    baseline_mean: float
    z_score: float
    risk_contribution: float
    unit: str


class IncidentListResponse(BaseModel):
    id: str
    resource_name: str
    resource_type: str
    resource_group: str
    location: str
    risk_score: float
    severity: str
    health_status: str
    detected_at: datetime
    estimated_cost_impact_usd: float
    summary: str


class IncidentDetailResponse(BaseModel):
    id: str
    resource_id: str
    resource_name: str
    resource_type: str
    resource_group: str
    location: str
    risk_score: float
    severity: str
    health_status: str
    health_reason: str
    is_platform_issue: bool
    anomaly_count: int
    contributing_metrics: list[ContributingMetricResponse]
    detected_at: datetime
    health_event_time: datetime | None
    time_window_start: datetime | None
    time_window_end: datetime | None
    summary: str
    root_cause_hypothesis: str
    recommended_action: str
    estimated_cost_impact_usd: float
    cost_impact_description: str


class KPIResponse(BaseModel):
    total_resources: int
    total_incidents: int
    critical_incidents: int
    high_incidents: int
    avg_risk_score: float
    total_estimated_cost_impact_usd: float
    last_refresh: datetime | None
    mode: str
