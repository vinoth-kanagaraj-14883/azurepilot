"""
Mock / deterministic summarizer.

Used when no LLM credentials are configured.  Generates template-based
summaries, root-cause hypotheses, and recommendations that are realistic
enough for demos and development.
"""
from __future__ import annotations

from analysis.correlation import Incident, Severity
from ingestion.models import HealthStatus, ResourceType

# --- Severity labels ---
_SEV_LABEL = {
    Severity.CRITICAL: "critical",
    Severity.HIGH: "high",
    Severity.MEDIUM: "moderate",
    Severity.LOW: "low",
    Severity.NONE: "minimal",
}

# --- Resource type friendly names ---
_TYPE_LABEL = {
    ResourceType.VIRTUAL_MACHINE: "Virtual Machine",
    ResourceType.APP_SERVICE: "App Service",
    ResourceType.STORAGE_ACCOUNT: "Storage Account",
}

# --- Health status phrases ---
_HEALTH_PHRASE = {
    HealthStatus.AVAILABLE: "is currently available",
    HealthStatus.DEGRADED: "is in a degraded state",
    HealthStatus.UNAVAILABLE: "is unavailable",
    HealthStatus.UNKNOWN: "has an unknown health status",
}


def _top_metric(incident: Incident) -> str | None:
    if incident.contributing_metrics:
        return incident.contributing_metrics[0].metric_name
    return None


def mock_summary(incident: Incident) -> str:
    rt = _TYPE_LABEL.get(incident.resource_type, incident.resource_type.value)
    hs = _HEALTH_PHRASE.get(incident.health_status, "has an unknown status")
    sev = _SEV_LABEL.get(incident.severity, "unknown")
    top = _top_metric(incident)

    base = (
        f"{rt} '{incident.resource_name}' in resource group '{incident.resource_group}' "
        f"{hs} with a {sev} risk score of {incident.risk_score:.0f}/100."
    )
    if top:
        m = incident.contributing_metrics[0]
        base += (
            f" The primary signal is elevated {top} "
            f"(current: {m.current_value:.1f}{m.unit}, "
            f"baseline: {m.baseline_mean:.1f}{m.unit})."
        )
    if incident.health_reason:
        base += f" Health event: {incident.health_reason}."
    return base


def mock_root_cause(incident: Incident) -> str:
    rt = _TYPE_LABEL.get(incident.resource_type, incident.resource_type.value)
    top = _top_metric(incident)

    if incident.is_platform_issue:
        return (
            f"This incident is likely caused by a platform-side issue on the Azure "
            f"infrastructure hosting '{incident.resource_name}'. "
            f"The Resource Health API reports: \"{incident.health_reason}\". "
            f"No workload-side changes are expected to resolve this; monitor the Azure "
            f"Service Health dashboard for further updates."
        )

    if incident.resource_type == ResourceType.VIRTUAL_MACHINE:
        if top == "Percentage CPU":
            return (
                f"The {rt} is experiencing a CPU spike well above its 24-hour baseline. "
                f"Likely causes: a runaway process, batch job, or increased traffic load. "
                f"The spike started recently and has not self-resolved, suggesting an "
                f"application-level issue rather than a transient Azure platform event."
            )
        elif top == "Available Memory Bytes":
            return (
                f"Available memory on '{incident.resource_name}' has dropped significantly. "
                f"This is consistent with a memory leak, a large in-memory dataset being loaded, "
                f"or insufficient VM size for current workload. OS-level OOM events may follow."
            )

    if incident.resource_type == ResourceType.APP_SERVICE:
        if top == "Http5xx":
            return (
                f"The App Service is returning a high rate of HTTP 5xx errors, "
                f"indicating server-side failures. Possible causes: recent deployment "
                f"introducing a bug, dependency failure (database, downstream API), "
                f"or configuration change. Check application logs and deployment history."
            )
        elif top == "HttpQueueLength":
            return (
                f"The HTTP request queue is growing, indicating the app cannot process "
                f"requests fast enough. This is typically caused by slow downstream calls, "
                f"CPU saturation, or insufficient instance count. Auto-scale rules may need tuning."
            )
        elif top == "AverageResponseTime":
            return (
                f"Response times are significantly above baseline, which may indicate "
                f"database query degradation, cold starts after a scale event, or a slow "
                f"external dependency. Correlate with database metrics and deployment events."
            )

    if incident.resource_type == ResourceType.STORAGE_ACCOUNT:
        if top == "Availability":
            return (
                f"Storage account availability has dropped below normal thresholds. "
                f"This could be a transient Azure Storage service issue or network "
                f"connectivity problem. Check the Azure Status page and storage account "
                f"metrics for throttling events (HTTP 503 responses)."
            )
        elif top == "SuccessE2ELatency":
            return (
                f"End-to-end latency for storage operations is significantly elevated. "
                f"Likely causes: storage throttling due to high transaction volume, "
                f"large object sizes, or cross-region access patterns. "
                f"Review the storage account's transaction metrics for 503/429 responses."
            )

    return (
        f"The {rt} '{incident.resource_name}' is showing anomalous behaviour across "
        f"{incident.anomaly_count} metric(s). Without a platform health event, "
        f"this is most likely a workload or configuration issue. "
        f"Review recent deployments, configuration changes, and application logs."
    )


def mock_recommendation(incident: Incident) -> str:
    rt = _TYPE_LABEL.get(incident.resource_type, incident.resource_type.value)
    top = _top_metric(incident)
    sev = incident.severity

    actions = []

    # Priority 0: Platform issue → wait and monitor
    if incident.is_platform_issue:
        actions.append(
            "1. Monitor the Azure Service Health dashboard "
            "(https://status.azure.com) for updates on the platform incident. "
            "No workload-side action is required until Azure resolves the underlying issue."
        )
        actions.append(
            "2. Consider failing over to a secondary region if your architecture supports it "
            "and the incident duration estimate exceeds your RTO."
        )
        actions.append(
            "3. Notify affected stakeholders and set a 30-minute re-check alarm."
        )
        return "\n".join(actions)

    # VM recommendations
    if incident.resource_type == ResourceType.VIRTUAL_MACHINE:
        if top == "Percentage CPU":
            actions.append(
                "1. SSH into the VM and run `top` / `htop` to identify the process consuming CPU. "
                "Kill or throttle runaway processes immediately."
            )
            actions.append(
                "2. If the load is legitimate (traffic spike), scale up the VM SKU or add "
                "a load-balanced instance to distribute the workload."
            )
            actions.append(
                "3. Review auto-scale policies; if not configured, set CPU-based scale-out "
                "at 70% threshold to prevent future incidents."
            )
        elif top == "Available Memory Bytes":
            actions.append(
                "1. Run `free -h` and `ps aux --sort=-%mem | head` on the VM to identify "
                "memory consumers. Restart the offending process or service."
            )
            actions.append(
                "2. If memory pressure is workload-driven, resize the VM to a larger SKU "
                "(e.g., move from D2s_v3 to D4s_v3)."
            )
            actions.append(
                "3. Check application code for memory leaks; profile with memory analysis tools."
            )
        else:
            actions.append(
                "1. Review VM performance metrics in Azure Monitor and correlate with "
                "application logs to pinpoint the root cause."
            )
            actions.append(
                "2. Restart the affected service or VM if safe to do so, and monitor for recovery."
            )

    # App Service recommendations
    elif incident.resource_type == ResourceType.APP_SERVICE:
        if top == "Http5xx":
            actions.append(
                "1. Check App Service logs in Log Analytics / Application Insights for "
                "exception stack traces. Identify the failing endpoint."
            )
            actions.append(
                "2. If a recent deployment is suspected, roll back using the Deployment Slots "
                "swap or redeploy the previous artifact."
            )
            actions.append(
                "3. Verify downstream dependencies (database, Redis, APIs) are healthy "
                "and not returning errors."
            )
        elif top in ("HttpQueueLength", "AverageResponseTime"):
            actions.append(
                "1. Scale out the App Service Plan immediately: increase instance count "
                "or enable auto-scale with appropriate CPU/queue-length triggers."
            )
            actions.append(
                "2. Identify slow operations using Application Insights Transaction Search; "
                "focus on the slowest database queries and external calls."
            )
            actions.append(
                "3. Enable App Service health checks and set up alert rules on "
                "HttpQueueLength > 20 for proactive notification."
            )
        else:
            actions.append(
                "1. Review Application Insights for error rates and slow dependencies."
            )
            actions.append(
                "2. Scale out the App Service Plan if CPU/memory is the bottleneck."
            )

    # Storage Account recommendations
    elif incident.resource_type == ResourceType.STORAGE_ACCOUNT:
        if top == "Availability":
            actions.append(
                "1. Check Azure Service Health for storage service advisories in your region. "
                "If confirmed platform issue, no action needed — monitor for updates."
            )
            actions.append(
                "2. Enable geo-redundant storage (GRS/RA-GRS) if not already configured "
                "to improve resilience for future incidents."
            )
            actions.append(
                "3. Review application retry logic to ensure it handles transient 503 errors "
                "gracefully with exponential back-off."
            )
        elif top == "SuccessE2ELatency":
            actions.append(
                "1. Check if the storage account is being throttled: review the "
                "`ClientThrottlingError` metric in Azure Monitor."
            )
            actions.append(
                "2. Distribute requests across multiple storage accounts or use "
                "Azure Blob Storage with CDN for read-heavy workloads."
            )
            actions.append(
                "3. Review blob access patterns; switch frequently-accessed blobs to "
                "Hot tier if they are currently in Cool/Archive."
            )
        else:
            actions.append(
                "1. Review storage account metrics for throttling (503/429 responses) "
                "and adjust request rate or increase redundancy."
            )

    if not actions:
        actions.append(
            "1. Review the incident details and correlate with recent changes "
            "(deployments, configuration updates, traffic patterns)."
        )
        actions.append(
            "2. Escalate to the on-call engineer if the issue does not self-resolve "
            f"within 15 minutes. Severity: {sev.value}."
        )

    return "\n".join(actions)
