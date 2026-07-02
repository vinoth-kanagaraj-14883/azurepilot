"""
Analysis orchestrator — ties together anomaly scoring, correlation, and cost overlay.
"""
from __future__ import annotations

import logging

from analysis.anomaly import compute_resource_risk
from analysis.correlation import Incident, correlate
from analysis.cost_overlay import CostImpact, estimate_cost_impact
from ingestion.models import AzureResource, HealthEvent, MetricSeries

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Runs the full analysis pipeline:
      1. Compute per-resource risk profiles from metric series.
      2. Correlate health events + risk profiles into incidents.
      3. Append cost impact estimates to each incident.
    """

    def analyze(
        self,
        resources: list[AzureResource],
        health_events: list[HealthEvent],
        all_metrics: dict[str, list[MetricSeries]],
        lookback_hours: int = 24,
    ) -> list[Incident]:
        """
        Args:
            resources:     All discovered resources
            health_events: Resource Health events (one per resource)
            all_metrics:   Dict mapping resource_id -> list of MetricSeries
            lookback_hours: Analysis time window

        Returns:
            List of Incident objects sorted by risk score (highest first)
        """
        logger.info("Computing risk profiles for %d resources", len(resources))
        risk_profiles = [
            compute_resource_risk(res.id, all_metrics.get(res.id, []))
            for res in resources
        ]

        logger.info("Correlating health + metric signals")
        incidents = correlate(
            resources=resources,
            health_events=health_events,
            risk_profiles=risk_profiles,
            lookback_hours=lookback_hours,
        )

        logger.info("Computing cost impact for %d incidents", len(incidents))
        for incident in incidents:
            cost = estimate_cost_impact(incident)
            incident.estimated_cost_impact_usd = cost.estimated_usd
            incident.cost_impact_description = cost.description

        return incidents

    def get_cost_impact(self, incident: Incident) -> CostImpact:
        return estimate_cost_impact(incident)
