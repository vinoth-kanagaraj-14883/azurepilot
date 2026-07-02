"""
FastAPI application — AzurePilot REST API.

Endpoints:
  GET /resources           — list monitored resources with risk scores
  GET /incidents           — list active incidents sorted by risk score
  GET /incidents/{id}      — incident detail with AI summary + cost impact
  GET /kpis                — KPI summary
  POST /refresh            — manually trigger pipeline re-run
"""
from __future__ import annotations

import logging
import statistics
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.pipeline import run_pipeline
from api.schemas import (
    IncidentDetailResponse,
    IncidentListResponse,
    KPIResponse,
    ResourceResponse,
)
from api.state import get_state
from analysis.correlation import Severity
from ingestion.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the pipeline once on startup."""
    logger.info("AzurePilot startup — running initial pipeline")
    try:
        resources, incidents = run_pipeline()
        get_state().update(resources, incidents)
    except Exception as exc:
        logger.error("Pipeline startup failed: %s", exc)
    yield


app = FastAPI(
    title="AzurePilot",
    description=(
        "AI-powered Azure monitoring copilot that combines Resource Health signals "
        "with Monitor Metrics to detect risky resources, explain root cause, and "
        "recommend next actions with cost-impact overlay."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the UI (served separately on port 3000 or 5173) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/resources", response_model=list[ResourceResponse], tags=["resources"])
def list_resources():
    """List all monitored Azure resources with current risk score and health status."""
    state = get_state()
    incident_map = {inc.resource_id: inc for inc in state.incidents}

    result = []
    for resource in state.resources:
        incident = incident_map.get(resource.id)
        result.append(
            ResourceResponse(
                id=resource.id,
                name=resource.name,
                resource_type=resource.resource_type.value,
                resource_group=resource.resource_group,
                location=resource.location,
                risk_score=incident.risk_score if incident else 0.0,
                health_status=(
                    incident.health_status.value if incident else "Unknown"
                ),
                severity=incident.severity.value if incident else "none",
            )
        )

    result.sort(key=lambda r: r.risk_score, reverse=True)
    return result


@app.get("/incidents", response_model=list[IncidentListResponse], tags=["incidents"])
def list_incidents():
    """List active incidents sorted by risk score (highest first)."""
    return [
        IncidentListResponse(
            id=inc.id,
            resource_name=inc.resource_name,
            resource_type=inc.resource_type.value,
            resource_group=inc.resource_group,
            location=inc.location,
            risk_score=inc.risk_score,
            severity=inc.severity.value,
            health_status=inc.health_status.value,
            detected_at=inc.detected_at,
            estimated_cost_impact_usd=inc.estimated_cost_impact_usd,
            summary=inc.summary,
        )
        for inc in get_state().incidents
    ]


@app.get("/incidents/{incident_id}", response_model=IncidentDetailResponse, tags=["incidents"])
def get_incident(incident_id: str):
    """Get full incident detail including AI summary, root cause, recommendation, and cost impact."""
    state = get_state()
    incident = next((inc for inc in state.incidents if inc.id == incident_id), None)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    return IncidentDetailResponse(
        id=incident.id,
        resource_id=incident.resource_id,
        resource_name=incident.resource_name,
        resource_type=incident.resource_type.value,
        resource_group=incident.resource_group,
        location=incident.location,
        risk_score=incident.risk_score,
        severity=incident.severity.value,
        health_status=incident.health_status.value,
        health_reason=incident.health_reason,
        is_platform_issue=incident.is_platform_issue,
        anomaly_count=incident.anomaly_count,
        contributing_metrics=[
            {
                "metric_name": m.metric_name,
                "current_value": m.current_value,
                "baseline_mean": m.baseline_mean,
                "z_score": m.z_score,
                "risk_contribution": m.risk_contribution,
                "unit": m.unit,
            }
            for m in incident.contributing_metrics
        ],
        detected_at=incident.detected_at,
        health_event_time=incident.health_event_time,
        time_window_start=incident.time_window_start,
        time_window_end=incident.time_window_end,
        summary=incident.summary,
        root_cause_hypothesis=incident.root_cause_hypothesis,
        recommended_action=incident.recommended_action,
        estimated_cost_impact_usd=incident.estimated_cost_impact_usd,
        cost_impact_description=incident.cost_impact_description,
    )


@app.get("/kpis", response_model=KPIResponse, tags=["kpis"])
def get_kpis():
    """KPI summary for the 'prove ROI' dashboard strip."""
    state = get_state()
    incidents = state.incidents
    settings = get_settings()

    risk_scores = [inc.risk_score for inc in incidents] if incidents else [0.0]
    avg_risk = statistics.mean(risk_scores) if risk_scores else 0.0

    return KPIResponse(
        total_resources=len(state.resources),
        total_incidents=len(incidents),
        critical_incidents=sum(1 for i in incidents if i.severity == Severity.CRITICAL),
        high_incidents=sum(1 for i in incidents if i.severity == Severity.HIGH),
        avg_risk_score=round(avg_risk, 1),
        total_estimated_cost_impact_usd=round(
            sum(i.estimated_cost_impact_usd for i in incidents), 2
        ),
        last_refresh=state.last_refresh,
        mode=settings.azurepilot_mode,
    )


@app.post("/refresh", tags=["admin"])
def refresh():
    """Manually trigger a full pipeline re-run."""
    try:
        resources, incidents = run_pipeline()
        get_state().update(resources, incidents)
        return {
            "status": "ok",
            "resources": len(resources),
            "incidents": len(incidents),
        }
    except Exception as exc:
        logger.error("Manual refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/health", tags=["admin"])
def health_check():
    """Simple health/readiness check."""
    return {"status": "ok", "version": "0.1.0"}
