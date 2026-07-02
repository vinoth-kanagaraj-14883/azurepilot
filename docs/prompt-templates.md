# AzurePilot — Prompt Templates

This document describes the LLM prompt templates used by AzurePilot's AI module
and how to tune them.

All templates are defined in `/ai/prompts.py` as Python string constants.

---

## System Prompt

Applied to every LLM call as the system message.

```
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
```

**Tuning tips:**
- Add your organisation's runbook URL structure to the system prompt so recommendations include direct links.
- Add your team's escalation path (e.g., "always mention PagerDuty policy X for critical incidents").
- Adjust tone: `"Be concise"` can be changed to `"Be thorough"` for written incident reports.

---

## 1. Incident Summary Template

**Purpose:** 2-3 sentence plain-English incident notification, suitable for Slack/Teams.

**Input variables:**
- `resource_name`, `resource_type`, `resource_group`
- `health_status`, `risk_score`, `severity`
- `health_reason`, `is_platform_issue`
- `contributing_metrics_text` (formatted list of top metric anomalies)

**Template:**
```
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
```

**Tuning tips:**
- Change `"2-3 sentences"` to `"one sentence"` for ultra-short Slack notifications.
- Add `"Include the affected user impact"` for customer-facing incident comms.
- Add `"Output only the summary text, no preamble"` to reduce LLM preamble text.

---

## 2. Root Cause Hypothesis Template

**Purpose:** Identify whether the root cause is platform-side or workload/config, with reasoning.

**Input variables:**
- `resource_name`, `resource_type`
- `health_status`, `health_reason`, `is_platform_issue`
- `risk_score`, `lookback_hours`
- `contributing_metrics_text`

**Template:**
```
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
```

**Tuning tips:**
- Add `"Reference specific Azure documentation links where relevant"` for more detailed output.
- Add historical incident context if available: `"Previous similar incident: {previous_incident_summary}"`.
- Adjust confidence language: add `"Rate your confidence: High / Medium / Low"` at the end.

---

## 3. Recommended Action Template

**Purpose:** 2-3 concrete next steps ordered by priority with rationale.

**Input variables:**
- `resource_name`, `resource_type`, `severity`
- `health_status`, `is_platform_issue`
- `risk_score`, `summary`, `root_cause`
- `cost_impact_usd`
- `contributing_metrics_text`

**Template:**
```
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
```

**Tuning tips:**
- Add `"Include the Azure Portal URL for each recommended action"` for direct links.
- Add `"Reference our internal runbook at https://wiki.yourcompany.com/runbooks"`.
- Add `"For severity=critical, always include an escalation step"`.
- Change `"2-3 actions"` to `"5 actions"` for comprehensive incident runbooks.

---

## Mock Summarizer

When no LLM credentials are configured, `/ai/mock_summarizer.py` provides
deterministic, template-based text for each of the three outputs.

The mock summarizer is scenario-aware:
- Different text for VM CPU spikes vs memory pressure vs App Service errors
- Distinguishes platform issues from workload issues
- Produces recommendations tailored to the top anomalous metric

To extend the mock summarizer, add new `if scenario == "..."` or
`if resource_type == ... and top == "..."` branches in the respective functions.

---

## Extending to New Resource Types

To add AI coverage for a new resource type (e.g., Azure SQL Database):

1. Add metric names to `ingestion/metrics_client.py` → `RESOURCE_METRICS`
2. Add the new `ResourceType` enum value to `ingestion/models.py`
3. Add scenario-specific text to `ai/mock_summarizer.py`
4. Add metric risk directions/thresholds to `analysis/anomaly.py`
5. Optionally tune the prompt templates to include SQL-specific context
