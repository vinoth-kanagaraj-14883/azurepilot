"""
Demo / mock data generator.

When AZUREPILOT_MODE=demo, this module provides realistic synthetic data
for VMs, App Services, and Storage Accounts without requiring any Azure
credentials.  Each run produces slightly randomised values so the UI
looks live.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from ingestion.models import (
    AzureResource,
    HealthEvent,
    HealthStatus,
    MetricDataPoint,
    MetricSeries,
    ResourceType,
)

# ---------------------------------------------------------------------------
# Seed resources
# ---------------------------------------------------------------------------

DEMO_RESOURCES: list[dict[str, Any]] = [
    # --- VMs ---
    {
        "name": "vm-prod-web-01",
        "resource_type": ResourceType.VIRTUAL_MACHINE,
        "resource_group": "rg-production",
        "location": "eastus",
        "scenario": "high_cpu",
    },
    {
        "name": "vm-prod-api-02",
        "resource_type": ResourceType.VIRTUAL_MACHINE,
        "resource_group": "rg-production",
        "location": "eastus",
        "scenario": "healthy",
    },
    {
        "name": "vm-staging-worker",
        "resource_type": ResourceType.VIRTUAL_MACHINE,
        "resource_group": "rg-staging",
        "location": "westus2",
        "scenario": "memory_pressure",
    },
    # --- App Services ---
    {
        "name": "app-customer-portal",
        "resource_type": ResourceType.APP_SERVICE,
        "resource_group": "rg-production",
        "location": "eastus",
        "scenario": "high_errors",
    },
    {
        "name": "app-internal-api",
        "resource_type": ResourceType.APP_SERVICE,
        "resource_group": "rg-production",
        "location": "eastus",
        "scenario": "queue_buildup",
    },
    {
        "name": "app-reporting",
        "resource_type": ResourceType.APP_SERVICE,
        "resource_group": "rg-analytics",
        "location": "westeurope",
        "scenario": "healthy",
    },
    # --- Storage Accounts ---
    {
        "name": "stprodlogs",
        "resource_type": ResourceType.STORAGE_ACCOUNT,
        "resource_group": "rg-production",
        "location": "eastus",
        "scenario": "degraded_availability",
    },
    {
        "name": "stprodbackup",
        "resource_type": ResourceType.STORAGE_ACCOUNT,
        "resource_group": "rg-production",
        "location": "eastus",
        "scenario": "high_latency",
    },
    {
        "name": "stanlytics",
        "resource_type": ResourceType.STORAGE_ACCOUNT,
        "resource_group": "rg-analytics",
        "location": "westeurope",
        "scenario": "healthy",
    },
]

SUBSCRIPTION_ID = "00000000-demo-0000-0000-000000000000"


def _resource_id(res: dict) -> str:
    rg = res["resource_group"]
    rt = res["resource_type"].value
    name = res["name"]
    return (
        f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{rg}/providers/{rt}/{name}"
    )


def get_demo_resources() -> list[AzureResource]:
    """Return the list of synthetic demo resources."""
    return [
        AzureResource(
            id=_resource_id(r),
            name=r["name"],
            resource_type=r["resource_type"],
            resource_group=r["resource_group"],
            location=r["location"],
            subscription_id=SUBSCRIPTION_ID,
            tags={"env": r["resource_group"].replace("rg-", ""), "demo": "true"},
        )
        for r in DEMO_RESOURCES
    ]


# ---------------------------------------------------------------------------
# Health events
# ---------------------------------------------------------------------------

_HEALTH_BY_SCENARIO: dict[str, tuple[HealthStatus, str, bool]] = {
    "high_cpu": (
        HealthStatus.DEGRADED,
        "VM is experiencing high CPU utilization affecting responsiveness",
        False,
    ),
    "memory_pressure": (
        HealthStatus.DEGRADED,
        "Memory pressure detected; workload may experience slowdowns",
        False,
    ),
    "high_errors": (
        HealthStatus.DEGRADED,
        "Elevated HTTP 5xx error rate detected on App Service",
        False,
    ),
    "queue_buildup": (
        HealthStatus.AVAILABLE,
        "Resource is available but HTTP queue is growing",
        False,
    ),
    "degraded_availability": (
        HealthStatus.UNAVAILABLE,
        "Storage service experiencing intermittent availability issues (platform investigation ongoing)",
        True,
    ),
    "high_latency": (
        HealthStatus.DEGRADED,
        "End-to-end latency is elevated; possible throttling",
        False,
    ),
    "healthy": (HealthStatus.AVAILABLE, "Resource is operating normally", False),
}


def get_demo_health_events() -> list[HealthEvent]:
    """Return synthetic health events for all demo resources."""
    now = datetime.now(tz=timezone.utc)
    events: list[HealthEvent] = []
    for r in DEMO_RESOURCES:
        scenario = r["scenario"]
        status, reason, is_platform = _HEALTH_BY_SCENARIO[scenario]
        occurred_offset = random.randint(15, 120)
        events.append(
            HealthEvent(
                resource_id=_resource_id(r),
                status=status,
                reason=reason,
                occurred_time=now - timedelta(minutes=occurred_offset),
                reported_time=now - timedelta(minutes=occurred_offset - 2),
                is_platform_issue=is_platform,
            )
        )
    return events


# ---------------------------------------------------------------------------
# Metric series generation
# ---------------------------------------------------------------------------

def _sine_wave(
    n_points: int,
    baseline: float,
    amplitude: float,
    noise_pct: float = 0.05,
    period: int = 288,  # one day in 5-min intervals
    phase: float = 0.0,
) -> list[float]:
    """Generate a realistic sine-wave time series with noise."""
    values = []
    for i in range(n_points):
        wave = baseline + amplitude * math.sin(2 * math.pi * (i + phase) / period)
        noise = wave * noise_pct * random.gauss(0, 1)
        values.append(max(0.0, wave + noise))
    return values


def _spike_at_end(
    values: list[float],
    spike_start_pct: float = 0.80,
    spike_multiplier: float = 2.5,
) -> list[float]:
    """Add a spike in the last portion of the series."""
    n = len(values)
    spike_start = int(n * spike_start_pct)
    return [
        v * spike_multiplier if i >= spike_start else v for i, v in enumerate(values)
    ]


def _make_series(
    resource_id: str,
    metric_name: str,
    values: list[float],
    unit: str,
    n_points: int,
    lookback_hours: int,
    aggregation: str = "Average",
) -> MetricSeries:
    now = datetime.now(tz=timezone.utc)
    interval_minutes = (lookback_hours * 60) // n_points or 5
    data_points = [
        MetricDataPoint(
            timestamp=now - timedelta(minutes=interval_minutes * (n_points - 1 - i)),
            value=round(values[i], 4),
            unit=unit,
        )
        for i in range(n_points)
    ]
    return MetricSeries(
        resource_id=resource_id,
        metric_name=metric_name,
        aggregation=aggregation,
        data_points=data_points,
    )


def get_demo_metrics(
    resource_id: str, resource_type: ResourceType, lookback_hours: int = 24
) -> list[MetricSeries]:
    """Generate synthetic metric time series for a resource."""
    n = 288  # 5-min intervals for 24 hours

    # Find scenario for this resource
    scenario = next(
        (r["scenario"] for r in DEMO_RESOURCES if _resource_id(r) == resource_id),
        "healthy",
    )

    if resource_type == ResourceType.VIRTUAL_MACHINE:
        return _vm_metrics(resource_id, scenario, n, lookback_hours)
    elif resource_type == ResourceType.APP_SERVICE:
        return _app_service_metrics(resource_id, scenario, n, lookback_hours)
    elif resource_type == ResourceType.STORAGE_ACCOUNT:
        return _storage_metrics(resource_id, scenario, n, lookback_hours)
    return []


def _vm_metrics(resource_id: str, scenario: str, n: int, hours: int) -> list[MetricSeries]:
    cpu_base = 30.0
    mem_base = 4.0 * 1024 ** 3  # 4 GB available

    cpu_vals = _sine_wave(n, cpu_base, 15.0, phase=random.uniform(0, 288))
    mem_vals = _sine_wave(n, mem_base, 0.5 * 1024 ** 3, phase=random.uniform(0, 288))

    if scenario == "high_cpu":
        cpu_vals = _spike_at_end(cpu_vals, spike_multiplier=2.8)
        cpu_vals = [min(99.9, v) for v in cpu_vals]
    elif scenario == "memory_pressure":
        mem_vals = [max(0, v * 0.2) for v in mem_vals]  # very low available memory

    net_in = _sine_wave(n, 50 * 1024 ** 2, 20 * 1024 ** 2)
    net_out = _sine_wave(n, 30 * 1024 ** 2, 10 * 1024 ** 2)
    disk_r = _sine_wave(n, 10 * 1024 ** 2, 5 * 1024 ** 2)
    disk_w = _sine_wave(n, 8 * 1024 ** 2, 3 * 1024 ** 2)

    return [
        _make_series(resource_id, "Percentage CPU", cpu_vals, "Percent", n, hours),
        _make_series(resource_id, "Available Memory Bytes", mem_vals, "Bytes", n, hours),
        _make_series(resource_id, "Network In Total", net_in, "Bytes", n, hours, "Total"),
        _make_series(resource_id, "Network Out Total", net_out, "Bytes", n, hours, "Total"),
        _make_series(resource_id, "Disk Read Bytes", disk_r, "Bytes", n, hours, "Total"),
        _make_series(resource_id, "Disk Write Bytes", disk_w, "Bytes", n, hours, "Total"),
    ]


def _app_service_metrics(resource_id: str, scenario: str, n: int, hours: int) -> list[MetricSeries]:
    req_base = 500.0
    cpu_secs = _sine_wave(n, 120.0, 40.0)
    http5xx = _sine_wave(n, 2.0, 1.0)
    queue_len = _sine_wave(n, 5.0, 3.0)
    avg_resp = _sine_wave(n, 200.0, 80.0)  # ms
    requests = _sine_wave(n, req_base, 150.0)
    mem_ws = _sine_wave(n, 400 * 1024 ** 2, 80 * 1024 ** 2)

    if scenario == "high_errors":
        http5xx = _spike_at_end(http5xx, spike_multiplier=15.0)
        avg_resp = _spike_at_end(avg_resp, spike_multiplier=3.0)
    elif scenario == "queue_buildup":
        queue_len = _spike_at_end(queue_len, spike_multiplier=8.0)
        avg_resp = _spike_at_end(avg_resp, spike_multiplier=2.0)

    return [
        _make_series(resource_id, "CpuTime", cpu_secs, "Seconds", n, hours, "Total"),
        _make_series(resource_id, "Http5xx", http5xx, "Count", n, hours, "Total"),
        _make_series(resource_id, "HttpQueueLength", queue_len, "Count", n, hours, "Average"),
        _make_series(resource_id, "AverageResponseTime", avg_resp, "Seconds", n, hours),
        _make_series(resource_id, "Requests", requests, "Count", n, hours, "Total"),
        _make_series(resource_id, "MemoryWorkingSet", mem_ws, "Bytes", n, hours),
    ]


def _storage_metrics(resource_id: str, scenario: str, n: int, hours: int) -> list[MetricSeries]:
    avail = _sine_wave(n, 99.9, 0.1)
    txns = _sine_wave(n, 5000.0, 1500.0)
    latency = _sine_wave(n, 10.0, 3.0)  # ms
    ingress = _sine_wave(n, 100 * 1024 ** 2, 30 * 1024 ** 2)
    egress = _sine_wave(n, 80 * 1024 ** 2, 20 * 1024 ** 2)

    if scenario == "degraded_availability":
        avail = [max(0.0, v - 40.0) for v in avail]  # drops to ~60%
    elif scenario == "high_latency":
        latency = _spike_at_end(latency, spike_multiplier=6.0)

    return [
        _make_series(resource_id, "Availability", avail, "Percent", n, hours),
        _make_series(resource_id, "Transactions", txns, "Count", n, hours, "Total"),
        _make_series(resource_id, "SuccessE2ELatency", latency, "MilliSeconds", n, hours),
        _make_series(resource_id, "Ingress", ingress, "Bytes", n, hours, "Total"),
        _make_series(resource_id, "Egress", egress, "Bytes", n, hours, "Total"),
    ]
