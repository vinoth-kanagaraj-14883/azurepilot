"""
In-memory state store for the AzurePilot prototype.

Holds the latest ingestion + analysis results so API endpoints can serve
them without re-running the full pipeline on every request.

In a production system this would be a database or cache (Redis, Cosmos DB, etc.).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from analysis.correlation import Incident
from ingestion.models import AzureResource

logger = logging.getLogger(__name__)


class AppState:
    """Thread-safe in-memory state for the API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._resources: list[AzureResource] = []
        self._incidents: list[Incident] = []
        self._last_refresh: datetime | None = None

    @property
    def resources(self) -> list[AzureResource]:
        with self._lock:
            return list(self._resources)

    @property
    def incidents(self) -> list[Incident]:
        with self._lock:
            return list(self._incidents)

    @property
    def last_refresh(self) -> datetime | None:
        with self._lock:
            return self._last_refresh

    def update(self, resources: list[AzureResource], incidents: list[Incident]) -> None:
        with self._lock:
            self._resources = resources
            self._incidents = incidents
            self._last_refresh = datetime.now(tz=timezone.utc)
        logger.info(
            "State updated: %d resources, %d incidents", len(resources), len(incidents)
        )


# Singleton
_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state
