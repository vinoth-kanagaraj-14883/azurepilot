"""
Resource discovery — list Azure resources of supported types within a subscription/RG.
"""
from __future__ import annotations

import logging

import httpx

from ingestion.models import AzureResource, ResourceType

logger = logging.getLogger(__name__)

RESOURCE_MANAGER_API_VERSION = "2021-04-01"
BASE_URL = "https://management.azure.com"

SUPPORTED_TYPES = [rt.value for rt in ResourceType]


class ResourceDiscovery:
    """Lists monitored Azure resources via the Resource Manager API."""

    def __init__(
        self,
        credential_token: str,
        subscription_id: str,
        resource_group: str = "",
    ) -> None:
        self._token = credential_token
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._headers = {"Authorization": "Bearer " + credential_token}

    def list_resources(self) -> list[AzureResource]:
        """Return all supported resources in the configured scope."""
        resources: list[AzureResource] = []
        for resource_type in SUPPORTED_TYPES:
            resources.extend(self._list_by_type(resource_type))
        return resources

    def _list_by_type(self, resource_type: str) -> list[AzureResource]:
        if self._resource_group:
            url = (
                f"{BASE_URL}/subscriptions/{self._subscription_id}"
                f"/resourceGroups/{self._resource_group}/providers/{resource_type}"
            )
        else:
            url = (
                f"{BASE_URL}/subscriptions/{self._subscription_id}"
                f"/providers/{resource_type}"
            )

        params: dict = {"api-version": RESOURCE_MANAGER_API_VERSION}
        results: list[AzureResource] = []

        try:
            with httpx.Client(timeout=60) as client:
                while url:
                    response = client.get(url, headers=self._headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    for item in data.get("value", []):
                        res = self._parse_resource(item)
                        if res:
                            results.append(res)
                    url = data.get("nextLink")
                    params = {}
        except Exception as exc:
            logger.warning("Resource discovery failed for %s: %s", resource_type, exc)

        return results

    @staticmethod
    def _parse_resource(item: dict) -> AzureResource | None:
        try:
            raw_type = item.get("type", "")
            # Normalise type casing to match enum values
            matched_type = next(
                (rt for rt in ResourceType if rt.value.lower() == raw_type.lower()), None
            )
            if matched_type is None:
                return None

            resource_id: str = item["id"]
            # Extract resource group from the resource ID
            parts = resource_id.split("/")
            rg_idx = next(
                (i for i, p in enumerate(parts) if p.lower() == "resourcegroups"), None
            )
            resource_group = parts[rg_idx + 1] if rg_idx is not None else ""
            sub_idx = next(
                (i for i, p in enumerate(parts) if p.lower() == "subscriptions"), None
            )
            subscription_id = parts[sub_idx + 1] if sub_idx is not None else ""

            return AzureResource(
                id=resource_id,
                name=item.get("name", ""),
                resource_type=matched_type,
                resource_group=resource_group,
                location=item.get("location", ""),
                subscription_id=subscription_id,
                tags=item.get("tags") or {},
            )
        except Exception as exc:
            logger.debug("Failed to parse resource item: %s", exc)
            return None
