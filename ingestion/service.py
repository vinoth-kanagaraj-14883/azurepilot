"""
Ingestion orchestrator — coordinates resource discovery, health, and metrics fetching.
Switches between demo/mock mode and live Azure mode based on AZUREPILOT_MODE env var.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ingestion.config import get_settings
from ingestion.models import AzureResource, HealthEvent, MetricSeries, ResourceType

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class IngestionService:
    """
    High-level ingestion service.

    In demo mode: returns synthetic data from demo_data module.
    In live mode: uses real Azure API clients with DefaultAzureCredential.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_resources(self) -> list[AzureResource]:
        if self._settings.is_demo:
            from ingestion.demo_data import get_demo_resources
            return get_demo_resources()
        return self._live_get_resources()

    def get_health_events(self) -> list[HealthEvent]:
        if self._settings.is_demo:
            from ingestion.demo_data import get_demo_health_events
            return get_demo_health_events()
        return self._live_get_health_events()

    def get_metrics_for_resource(
        self, resource: AzureResource
    ) -> list[MetricSeries]:
        if self._settings.is_demo:
            from ingestion.demo_data import get_demo_metrics
            return get_demo_metrics(
                resource.id,
                resource.resource_type,
                lookback_hours=self._settings.metrics_lookback_hours,
            )
        return self._live_get_metrics(resource)

    # ------------------------------------------------------------------
    # Live mode helpers (require real Azure credentials)
    # ------------------------------------------------------------------

    def _get_credential_token(self) -> str:
        """
        Obtain a bearer token via DefaultAzureCredential.
        Supports: Managed Identity, Service Principal env vars, az CLI login.
        """
        from azure.identity import DefaultAzureCredential  # type: ignore[import]

        credential = DefaultAzureCredential()
        token = credential.get_token("https://management.azure.com/.default")
        return token.token

    def _live_get_resources(self) -> list[AzureResource]:
        from ingestion.resource_discovery import ResourceDiscovery

        token = self._get_credential_token()
        discovery = ResourceDiscovery(
            credential_token=token,
            subscription_id=self._settings.azure_subscription_id,
            resource_group=self._settings.azure_resource_group,
        )
        return discovery.list_resources()

    def _live_get_health_events(self) -> list[HealthEvent]:
        from ingestion.health_client import ResourceHealthClient

        token = self._get_credential_token()
        client = ResourceHealthClient(
            credential_token=token,
            subscription_id=self._settings.azure_subscription_id,
        )
        return client.get_availability_statuses_for_subscription()

    def _live_get_metrics(self, resource: AzureResource) -> list[MetricSeries]:
        from ingestion.metrics_client import MonitorMetricsClient

        token = self._get_credential_token()
        client = MonitorMetricsClient(credential_token=token)
        return client.get_metrics_for_resource_type(
            resource_id=resource.id,
            resource_type=resource.resource_type.value,
            lookback_hours=self._settings.metrics_lookback_hours,
        )
