"""
Pipeline runner — orchestrates ingestion -> analysis -> AI enrichment.
"""
from __future__ import annotations

import logging

from ai.service import AIService
from analysis.service import AnalysisService
from ingestion.config import get_settings
from ingestion.service import IngestionService

logger = logging.getLogger(__name__)


def run_pipeline() -> tuple[list, list]:
    """
    Run the full AzurePilot pipeline:
      1. Ingest resources, health events, and metrics
      2. Analyse: compute risk scores, correlate, estimate cost
      3. Enrich with AI summaries

    Returns:
        (resources, incidents) tuple
    """
    settings = get_settings()
    ingestion = IngestionService()
    analysis = AnalysisService()
    ai = AIService()

    logger.info("Starting AzurePilot pipeline (mode=%s)", settings.azurepilot_mode)

    # --- 1. Ingestion ---
    resources = ingestion.get_resources()
    logger.info("Discovered %d resources", len(resources))

    health_events = ingestion.get_health_events()
    logger.info("Fetched %d health events", len(health_events))

    all_metrics: dict = {}
    for resource in resources:
        metrics = ingestion.get_metrics_for_resource(resource)
        all_metrics[resource.id] = metrics
    logger.info("Fetched metrics for %d resources", len(all_metrics))

    # --- 2. Analysis ---
    incidents = analysis.analyze(
        resources=resources,
        health_events=health_events,
        all_metrics=all_metrics,
        lookback_hours=settings.metrics_lookback_hours,
    )
    logger.info("Produced %d incidents", len(incidents))

    # --- 3. AI enrichment ---
    for incident in incidents:
        ai.enrich_incident(incident)
    logger.info("AI enrichment complete")

    return resources, incidents
