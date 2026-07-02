"""
Azure Monitor Metrics API client.

API reference:
  https://learn.microsoft.com/en-us/rest/api/monitor/metrics/list
  Stable API version: 2023-10-01
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx

from ingestion.models import MetricDataPoint, MetricSeries

logger = logging.getLogger(__name__)

MONITOR_METRICS_API_VERSION = "2023-10-01"

# Supported metrics per resource type
RESOURCE_METRICS: dict[str, list[str]] = {
    "Microsoft.Compute/virtualMachines": [
        "Percentage CPU",
        "Available Memory Bytes",
        "Network In Total",
        "Network Out Total",
        "Disk Read Bytes",
        "Disk Write Bytes",
    ],
    "Microsoft.Web/sites": [
        "CpuTime",
        "Http5xx",
        "HttpQueueLength",
        "AverageResponseTime",
        "Requests",
        "MemoryWorkingSet",
    ],
    "Microsoft.Storage/storageAccounts": [
        "Availability",
        "Transactions",
        "SuccessE2ELatency",
        "Ingress",
        "Egress",
    ],
}


class MonitorMetricsClient:
    """
    Fetches Azure Monitor metric time series for a resource.
    """

    BASE_URL = "https://management.azure.com"

    def __init__(self, credential_token: str) -> None:
        self._token = credential_token
        self._headers = {"Authorization": "Bearer " + credential_token}

    def get_metrics(
        self,
        resource_id: str,
        metric_names: list[str],
        lookback_hours: int = 24,
        interval: str = "PT5M",
        aggregation: Literal["Average", "Total", "Minimum", "Maximum", "Count"] = "Average",
    ) -> list[MetricSeries]:
        """
        Fetch metric time series for a resource.

        Args:
            resource_id:    Full Azure resource ID
            metric_names:   List of metric names (Azure Monitor metric name strings)
            lookback_hours: How many hours of history to fetch
            interval:       ISO 8601 duration for data point granularity
            aggregation:    Aggregation type

        Returns:
            List of MetricSeries, one per metric name
        """
        end_time = datetime.now(tz=timezone.utc)
        start_time = end_time - timedelta(hours=lookback_hours)
        timespan = (
            f"{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
            f"{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        url = f"{self.BASE_URL}{resource_id}/providers/Microsoft.Insights/metrics"
        params = {
            "api-version": MONITOR_METRICS_API_VERSION,
            "metricnames": ",".join(metric_names),
            "timespan": timespan,
            "interval": interval,
            "aggregation": aggregation,
        }

        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Monitor Metrics API error for %s: %s", resource_id, exc.response.status_code
            )
            return []
        except Exception as exc:
            logger.warning("Monitor Metrics request failed for %s: %s", resource_id, exc)
            return []

        return self._parse_metrics(resource_id, data, aggregation)

    def get_metrics_for_resource_type(
        self,
        resource_id: str,
        resource_type: str,
        lookback_hours: int = 24,
    ) -> list[MetricSeries]:
        """Convenience method that uses the default metrics for a resource type."""
        metric_names = RESOURCE_METRICS.get(resource_type, [])
        if not metric_names:
            logger.warning("No metrics configured for resource type: %s", resource_type)
            return []
        return self.get_metrics(resource_id, metric_names, lookback_hours=lookback_hours)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_metrics(
        self, resource_id: str, data: dict, aggregation: str
    ) -> list[MetricSeries]:
        series_list: list[MetricSeries] = []

        agg_lower = aggregation.lower()

        for metric in data.get("value", []):
            metric_name = metric.get("name", {}).get("value", "unknown")
            unit = metric.get("unit", "")

            data_points: list[MetricDataPoint] = []
            for ts in metric.get("timeseries", []):
                for dp in ts.get("data", []):
                    raw_value = (
                        dp.get(agg_lower)
                        or dp.get("average")
                        or dp.get("total")
                        or 0.0
                    )
                    if raw_value is None:
                        continue
                    try:
                        ts_dt = datetime.fromisoformat(
                            dp["timeStamp"].replace("Z", "+00:00")
                        )
                    except (KeyError, ValueError):
                        continue
                    data_points.append(
                        MetricDataPoint(timestamp=ts_dt, value=float(raw_value), unit=unit)
                    )

            series_list.append(
                MetricSeries(
                    resource_id=resource_id,
                    metric_name=metric_name,
                    aggregation=aggregation,
                    data_points=data_points,
                )
            )

        return series_list
