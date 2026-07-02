"""
Integration tests for the FastAPI endpoints.

These tests use the TestClient (httpx) and run the full pipeline in demo mode,
so they don't require any Azure credentials.
"""
from __future__ import annotations

import os
import pytest

# Ensure demo mode for tests
os.environ.setdefault("AZUREPILOT_MODE", "demo")

from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client with the API app."""
    from api.main import app
    from api.pipeline import run_pipeline
    from api.state import get_state

    # Run pipeline once before tests
    resources, incidents = run_pipeline()
    get_state().update(resources, incidents)

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_returns_version(self, client):
        response = client.get("/health")
        assert "version" in response.json()


class TestResourcesEndpoint:
    def test_returns_list(self, client):
        response = client.get("/resources")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_resources_not_empty_in_demo(self, client):
        response = client.get("/resources")
        resources = response.json()
        assert len(resources) > 0

    def test_resource_fields(self, client):
        response = client.get("/resources")
        resource = response.json()[0]
        required_fields = {"id", "name", "resource_type", "resource_group", "location", "risk_score", "health_status", "severity"}
        assert required_fields.issubset(set(resource.keys()))

    def test_resources_sorted_by_risk_score(self, client):
        response = client.get("/resources")
        resources = response.json()
        scores = [r["risk_score"] for r in resources]
        assert scores == sorted(scores, reverse=True)

    def test_risk_score_bounded(self, client):
        response = client.get("/resources")
        for resource in response.json():
            assert 0.0 <= resource["risk_score"] <= 100.0

    def test_covers_all_resource_types(self, client):
        response = client.get("/resources")
        types = {r["resource_type"] for r in response.json()}
        assert "Microsoft.Compute/virtualMachines" in types
        assert "Microsoft.Web/sites" in types
        assert "Microsoft.Storage/storageAccounts" in types


class TestIncidentsEndpoint:
    def test_returns_list(self, client):
        response = client.get("/incidents")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_incidents_not_empty_in_demo(self, client):
        response = client.get("/incidents")
        assert len(response.json()) > 0

    def test_incident_list_fields(self, client):
        response = client.get("/incidents")
        incident = response.json()[0]
        required = {
            "id", "resource_name", "resource_type", "resource_group",
            "location", "risk_score", "severity", "health_status",
            "detected_at", "estimated_cost_impact_usd", "summary",
        }
        assert required.issubset(set(incident.keys()))

    def test_incidents_sorted_by_risk_score(self, client):
        response = client.get("/incidents")
        incidents = response.json()
        scores = [i["risk_score"] for i in incidents]
        assert scores == sorted(scores, reverse=True)

    def test_incidents_have_summaries(self, client):
        response = client.get("/incidents")
        for incident in response.json():
            # In demo mode, all incidents should have mock summaries
            assert incident["summary"]

    def test_incidents_include_multiple_resource_types(self, client):
        response = client.get("/incidents")
        types = {i["resource_type"] for i in response.json()}
        # Demo mode should produce incidents across all 3 resource types
        assert len(types) >= 2


class TestIncidentDetailEndpoint:
    def _get_first_incident_id(self, client) -> str:
        response = client.get("/incidents")
        return response.json()[0]["id"]

    def test_returns_detail(self, client):
        incident_id = self._get_first_incident_id(client)
        response = client.get(f"/incidents/{incident_id}")
        assert response.status_code == 200

    def test_detail_fields(self, client):
        incident_id = self._get_first_incident_id(client)
        response = client.get(f"/incidents/{incident_id}")
        data = response.json()
        required = {
            "id", "resource_id", "resource_name", "resource_type",
            "risk_score", "severity", "health_status", "health_reason",
            "is_platform_issue", "anomaly_count", "contributing_metrics",
            "detected_at", "summary", "root_cause_hypothesis",
            "recommended_action", "estimated_cost_impact_usd",
            "cost_impact_description",
        }
        assert required.issubset(set(data.keys()))

    def test_detail_has_ai_content(self, client):
        incident_id = self._get_first_incident_id(client)
        response = client.get(f"/incidents/{incident_id}")
        data = response.json()
        assert data["summary"]
        assert data["root_cause_hypothesis"]
        assert data["recommended_action"]

    def test_contributing_metrics_structure(self, client):
        incident_id = self._get_first_incident_id(client)
        response = client.get(f"/incidents/{incident_id}")
        data = response.json()
        for m in data["contributing_metrics"]:
            assert "metric_name" in m
            assert "current_value" in m
            assert "baseline_mean" in m
            assert "z_score" in m
            assert "risk_contribution" in m

    def test_nonexistent_incident_returns_404(self, client):
        response = client.get("/incidents/nonexistent-id-12345")
        assert response.status_code == 404

    def test_cost_impact_non_negative(self, client):
        incident_id = self._get_first_incident_id(client)
        response = client.get(f"/incidents/{incident_id}")
        assert response.json()["estimated_cost_impact_usd"] >= 0.0


class TestKPIsEndpoint:
    def test_returns_kpis(self, client):
        response = client.get("/kpis")
        assert response.status_code == 200

    def test_kpi_fields(self, client):
        response = client.get("/kpis")
        data = response.json()
        required = {
            "total_resources", "total_incidents", "critical_incidents",
            "high_incidents", "avg_risk_score", "total_estimated_cost_impact_usd",
            "last_refresh", "mode",
        }
        assert required.issubset(set(data.keys()))

    def test_mode_is_demo(self, client):
        response = client.get("/kpis")
        assert response.json()["mode"] == "demo"

    def test_kpi_counts_non_negative(self, client):
        response = client.get("/kpis")
        data = response.json()
        assert data["total_resources"] >= 0
        assert data["total_incidents"] >= 0
        assert data["critical_incidents"] >= 0
        assert data["high_incidents"] >= 0

    def test_avg_risk_score_bounded(self, client):
        response = client.get("/kpis")
        assert 0.0 <= response.json()["avg_risk_score"] <= 100.0

    def test_cost_impact_non_negative(self, client):
        response = client.get("/kpis")
        assert response.json()["total_estimated_cost_impact_usd"] >= 0.0
