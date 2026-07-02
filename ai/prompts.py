"""
Prompt templates for AzurePilot AI outputs.

These templates are stored as Python constants and can be customised or
externalised to files.  See /docs/prompt-templates.md for documentation.
"""

# ---------------------------------------------------------------------------
# System prompt — shared across all calls
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are AzurePilot, an expert Azure SRE / cloud operations AI assistant.
Your role is to analyse Azure resource health and monitoring metric data and
provide clear, actionable intelligence to cloud/SRE engineers.

Guidelines:
- Be concise and direct. Engineers are busy; avoid waffle.
- Use specific numbers from the data provided.
- Distinguish between platform-side issues (Azure outage/degradation) and
  workload/configuration issues.
- Recommended actions should be concrete and ordered by priority.
- Format responses in plain prose (no markdown headers or bullets unless requested).
"""

# ---------------------------------------------------------------------------
# Incident summary template
# ---------------------------------------------------------------------------

INCIDENT_SUMMARY_TEMPLATE = """\
Summarise the following Azure resource health incident in 2-3 sentences.
Focus on what is happening, which resource is affected, and how severe it is.

Resource: {resource_name} ({resource_type})
Resource Group: {resource_group}
Health Status: {health_status}
Risk Score: {risk_score}/100
Severity: {severity}
Health Reason: {health_reason}
Platform Issue: {is_platform_issue}
Top Contributing Metrics:
{contributing_metrics_text}

Provide a plain-English summary suitable for an incident Slack notification.
"""

# ---------------------------------------------------------------------------
# Root cause hypothesis template
# ---------------------------------------------------------------------------

ROOT_CAUSE_TEMPLATE = """\
Based on the Azure resource health and metric data below, provide a concise
root cause hypothesis (2-4 sentences).  State whether this is more likely a
platform issue (Azure infrastructure) or a workload/configuration issue.
Explain your reasoning using the specific metric values provided.

Resource: {resource_name} ({resource_type})
Health Status: {health_status} — "{health_reason}"
Platform-Initiated: {is_platform_issue}
Risk Score: {risk_score}/100
Analysis Window: last {lookback_hours} hours

Metric Anomalies:
{contributing_metrics_text}

Root cause hypothesis:
"""

# ---------------------------------------------------------------------------
# Recommended action template
# ---------------------------------------------------------------------------

RECOMMENDED_ACTION_TEMPLATE = """\
Given the following Azure incident details, provide 2-3 concrete recommended
actions an SRE engineer should take right now, in priority order.
Include the rationale for each action.

Resource: {resource_name} ({resource_type})
Severity: {severity}
Health Status: {health_status}
Platform Issue: {is_platform_issue}
Risk Score: {risk_score}/100
Summary: {summary}
Root Cause: {root_cause}
Estimated Cost Impact: ${cost_impact_usd:.2f}

Top metric signals:
{contributing_metrics_text}

Recommended actions:
"""


# ---------------------------------------------------------------------------
# Helper: format contributing metrics for prompt injection
# ---------------------------------------------------------------------------

def format_contributing_metrics(contributing_metrics: list[dict]) -> str:
    if not contributing_metrics:
        return "  (no significant metric anomalies detected)"
    lines = []
    for m in contributing_metrics[:5]:  # top 5
        lines.append(
            f"  - {m['metric_name']}: current={m['current_value']:.2f}{m.get('unit','')}, "
            f"baseline={m['baseline_mean']:.2f}{m.get('unit','')}, "
            f"z-score={m['z_score']:.1f}, risk contribution={m['risk_contribution']:.0f}/100"
        )
    return "\n".join(lines)
