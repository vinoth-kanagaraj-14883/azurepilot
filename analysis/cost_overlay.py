"""
Cost Overlay Stub

Provides a structured interface for estimating the dollar impact of an incident.

NOTE: This is a STUB implementation that returns mocked cost estimates.
      It is designed with a clean interface so it can be wired to the real
      Azure Cost Management API (https://learn.microsoft.com/en-us/rest/api/cost-management/)
      in a future iteration without changing the caller interface.

      To replace with real data:
        1. Implement `_fetch_resource_daily_cost(resource_id) -> float` using
           Azure Cost Management REST API or azure-mgmt-costmanagement SDK.
        2. Multiply the daily cost by the estimated downtime/degradation fraction.
        3. Remove the mock logic below.
"""
from __future__ import annotations

from pydantic import BaseModel

from analysis.correlation import Incident, Severity

# Mock hourly costs by resource type (USD) — rough market estimates
_MOCK_HOURLY_COST: dict[str, float] = {
    "Microsoft.Compute/virtualMachines": 0.50,
    "Microsoft.Web/sites": 0.15,
    "Microsoft.Storage/storageAccounts": 0.05,
}

# Downtime/degradation fraction by severity
_SEVERITY_IMPACT_FRACTION: dict[Severity, float] = {
    Severity.CRITICAL: 0.80,
    Severity.HIGH: 0.40,
    Severity.MEDIUM: 0.15,
    Severity.LOW: 0.05,
    Severity.NONE: 0.0,
}

# Estimated hours until resolution by severity
_SEVERITY_HOURS_TO_RESOLVE: dict[Severity, float] = {
    Severity.CRITICAL: 4.0,
    Severity.HIGH: 2.0,
    Severity.MEDIUM: 1.0,
    Severity.LOW: 0.5,
    Severity.NONE: 0.0,
}


class CostImpact(BaseModel):
    """Structured cost impact estimate for an incident."""

    estimated_usd: float
    """Estimated dollar impact (downtime + wasted spend)."""

    hourly_resource_cost_usd: float
    """Approximate hourly cost of the resource."""

    impact_fraction: float
    """Fraction of resource capacity/availability affected (0-1)."""

    hours_to_resolve: float
    """Estimated hours until the issue resolves if not actioned."""

    description: str
    """Human-readable summary of the cost estimate."""

    is_stub: bool = True
    """Always True for this stub; set to False when wired to real Cost Management API."""


def estimate_cost_impact(incident: Incident) -> CostImpact:
    """
    Estimate the dollar impact of an incident.

    STUB: Returns a mocked estimate based on resource type, severity, and
    rough hourly cost approximations.

    Args:
        incident: The correlated incident to estimate cost for.

    Returns:
        CostImpact with estimated dollar impact and metadata.
    """
    resource_type = incident.resource_type.value
    hourly_cost = _MOCK_HOURLY_COST.get(resource_type, 0.10)
    impact_fraction = _SEVERITY_IMPACT_FRACTION.get(incident.severity, 0.0)
    hours = _SEVERITY_HOURS_TO_RESOLVE.get(incident.severity, 0.0)

    estimated_usd = hourly_cost * impact_fraction * hours

    if estimated_usd == 0.0:
        description = "No significant cost impact estimated."
    else:
        description = (
            f"Estimated ${estimated_usd:.2f} in wasted/lost spend "
            f"({impact_fraction * 100:.0f}% impact on a ${hourly_cost:.2f}/hr resource "
            f"for ~{hours:.1f} hours until resolution). "
            "Note: this is a stub estimate — wire to Azure Cost Management API for actuals."
        )

    return CostImpact(
        estimated_usd=round(estimated_usd, 2),
        hourly_resource_cost_usd=hourly_cost,
        impact_fraction=impact_fraction,
        hours_to_resolve=hours,
        description=description,
    )
