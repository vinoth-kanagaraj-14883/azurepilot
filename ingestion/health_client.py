"""
Azure Resource Health API client.

API reference:
  https://learn.microsoft.com/en-us/rest/api/resourcehealth/availability-statuses
  Stable API version: 2022-10-01
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ingestion.models import HealthEvent, HealthStatus

logger = logging.getLogger(__name__)

RESOURCE_HEALTH_API_VERSION = "2022-10-01"


class ResourceHealthClient:
    """
    Fetches Azure Resource Health availability statuses for resources.

    Requires a bearer token (obtained via azure-identity DefaultAzureCredential).
    """

    BASE_URL = "https://management.azure.com"

    def __init__(self, credential_token: str, subscription_id: str) -> None:
        self._token = credential_token
        self._subscription_id = subscription_id
        self._headers = {"Authorization": "Bearer " + credential_token}

    def get_availability_status(self, resource_id: str) -> HealthEvent:
        """
        Fetch the current availability status for a single resource.

        Args:
            resource_id: Full Azure resource ID
                e.g. /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{name}
        """
        url = (
            f"{self.BASE_URL}{resource_id}"
            f"/providers/Microsoft.ResourceHealth/availabilityStatuses/current"
        )
        params = {"api-version": RESOURCE_HEALTH_API_VERSION}

        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Resource Health API error for %s: %s", resource_id, exc.response.status_code
            )
            return self._unknown_event(resource_id)
        except Exception as exc:
            logger.warning("Resource Health request failed for %s: %s", resource_id, exc)
            return self._unknown_event(resource_id)

        return self._parse_availability_status(resource_id, data)

    def get_availability_statuses_for_subscription(self) -> list[HealthEvent]:
        """List availability statuses for all resources in the subscription."""
        url = (
            f"{self.BASE_URL}/subscriptions/{self._subscription_id}"
            f"/providers/Microsoft.ResourceHealth/availabilityStatuses"
        )
        params = {"api-version": RESOURCE_HEALTH_API_VERSION}

        events: list[HealthEvent] = []
        try:
            with httpx.Client(timeout=60) as client:
                while url:
                    response = client.get(url, headers=self._headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    for item in data.get("value", []):
                        rid = item.get("id", "").split(
                            "/providers/Microsoft.ResourceHealth"
                        )[0]
                        events.append(self._parse_availability_status(rid, item))
                    url = data.get("nextLink")
                    params = {}  # nextLink already includes params
        except Exception as exc:
            logger.error("Failed to list availability statuses: %s", exc)

        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_availability_status(self, resource_id: str, data: dict) -> HealthEvent:
        props = data.get("properties", {})
        raw_status = props.get("availabilityState", "Unknown")
        status = self._map_status(raw_status)
        reason_type = props.get("reasonType", "")
        summary = props.get("summary", "")
        occurred_time_str = props.get("occurredTime") or props.get("reportedTime") or ""
        reported_time_str = props.get("reportedTime") or ""

        try:
            occurred_time = datetime.fromisoformat(occurred_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            occurred_time = datetime.now(tz=timezone.utc)

        try:
            reported_time = datetime.fromisoformat(reported_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            reported_time = datetime.now(tz=timezone.utc)

        return HealthEvent(
            resource_id=resource_id,
            status=status,
            reason=summary or reason_type,
            occurred_time=occurred_time,
            reported_time=reported_time,
            is_platform_issue=reason_type.lower() in ("platforminitiated", "platform"),
        )

    @staticmethod
    def _map_status(raw: str) -> HealthStatus:
        mapping = {
            "Available": HealthStatus.AVAILABLE,
            "Unavailable": HealthStatus.UNAVAILABLE,
            "Degraded": HealthStatus.DEGRADED,
            "Unknown": HealthStatus.UNKNOWN,
        }
        return mapping.get(raw, HealthStatus.UNKNOWN)

    @staticmethod
    def _unknown_event(resource_id: str) -> HealthEvent:
        now = datetime.now(tz=timezone.utc)
        return HealthEvent(
            resource_id=resource_id,
            status=HealthStatus.UNKNOWN,
            reason="Could not retrieve health status",
            occurred_time=now,
            reported_time=now,
        )
