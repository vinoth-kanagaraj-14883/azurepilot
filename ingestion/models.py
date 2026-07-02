"""
Shared data models for AzurePilot ingestion layer.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    VIRTUAL_MACHINE = "Microsoft.Compute/virtualMachines"
    APP_SERVICE = "Microsoft.Web/sites"
    STORAGE_ACCOUNT = "Microsoft.Storage/storageAccounts"


class HealthStatus(str, Enum):
    AVAILABLE = "Available"
    UNAVAILABLE = "Unavailable"
    DEGRADED = "Degraded"
    UNKNOWN = "Unknown"


class AzureResource(BaseModel):
    """Represents a monitored Azure resource."""

    id: str
    name: str
    resource_type: ResourceType
    resource_group: str
    location: str
    subscription_id: str
    tags: dict[str, str] = Field(default_factory=dict)


class HealthEvent(BaseModel):
    """Represents a Resource Health availability status."""

    resource_id: str
    status: HealthStatus
    reason: str = ""
    occurred_time: datetime
    reported_time: datetime
    is_platform_issue: bool = False


class MetricDataPoint(BaseModel):
    """A single data point in a metric time series."""

    timestamp: datetime
    value: float
    unit: str = ""


class MetricSeries(BaseModel):
    """Metric time series for a resource."""

    resource_id: str
    metric_name: str
    aggregation: str
    data_points: list[MetricDataPoint]
    metadata: dict[str, Any] = Field(default_factory=dict)
