"""
Provider-agnostic LLM service wrapper.

Provider selection (in priority order):
  1. Azure OpenAI — if AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY are set
  2. OpenAI — if OPENAI_API_KEY is set
  3. Mock summarizer — deterministic template-based (no API key needed)

The same interface is used regardless of provider, so switching providers
requires only env var changes.
"""
from __future__ import annotations

import logging

from analysis.correlation import Incident
from ai.prompts import (
    INCIDENT_SUMMARY_TEMPLATE,
    ROOT_CAUSE_TEMPLATE,
    RECOMMENDED_ACTION_TEMPLATE,
    SYSTEM_PROMPT,
    format_contributing_metrics,
)
from ingestion.config import get_settings

logger = logging.getLogger(__name__)


class AIService:
    """
    Generates AI-powered incident summaries, root cause hypotheses,
    and recommended actions.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._provider = self._settings.llm_provider
        logger.info("AIService initialised with provider: %s", self._provider)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich_incident(self, incident: Incident) -> Incident:
        """
        Populate the summary, root_cause_hypothesis, and recommended_action
        fields of an Incident in place.
        """
        incident.summary = self.generate_summary(incident)
        incident.root_cause_hypothesis = self.generate_root_cause(incident)
        incident.recommended_action = self.generate_recommendation(incident)
        return incident

    def generate_summary(self, incident: Incident) -> str:
        if self._provider == "mock":
            from ai.mock_summarizer import mock_summary
            return mock_summary(incident)
        metrics_text = format_contributing_metrics(
            [m.model_dump() for m in incident.contributing_metrics]
        )
        prompt = INCIDENT_SUMMARY_TEMPLATE.format(
            resource_name=incident.resource_name,
            resource_type=incident.resource_type.value,
            resource_group=incident.resource_group,
            health_status=incident.health_status.value,
            risk_score=incident.risk_score,
            severity=incident.severity.value,
            health_reason=incident.health_reason or "N/A",
            is_platform_issue=incident.is_platform_issue,
            contributing_metrics_text=metrics_text,
        )
        return self._complete(prompt)

    def generate_root_cause(self, incident: Incident) -> str:
        if self._provider == "mock":
            from ai.mock_summarizer import mock_root_cause
            return mock_root_cause(incident)
        metrics_text = format_contributing_metrics(
            [m.model_dump() for m in incident.contributing_metrics]
        )
        lookback = self._settings.metrics_lookback_hours
        prompt = ROOT_CAUSE_TEMPLATE.format(
            resource_name=incident.resource_name,
            resource_type=incident.resource_type.value,
            health_status=incident.health_status.value,
            health_reason=incident.health_reason or "N/A",
            is_platform_issue=incident.is_platform_issue,
            risk_score=incident.risk_score,
            lookback_hours=lookback,
            contributing_metrics_text=metrics_text,
        )
        return self._complete(prompt)

    def generate_recommendation(self, incident: Incident) -> str:
        if self._provider == "mock":
            from ai.mock_summarizer import mock_recommendation
            return mock_recommendation(incident)
        metrics_text = format_contributing_metrics(
            [m.model_dump() for m in incident.contributing_metrics]
        )
        prompt = RECOMMENDED_ACTION_TEMPLATE.format(
            resource_name=incident.resource_name,
            resource_type=incident.resource_type.value,
            severity=incident.severity.value,
            health_status=incident.health_status.value,
            is_platform_issue=incident.is_platform_issue,
            risk_score=incident.risk_score,
            summary=incident.summary or "(summary not yet generated)",
            root_cause=incident.root_cause_hypothesis or "(root cause not yet determined)",
            cost_impact_usd=incident.estimated_cost_impact_usd,
            contributing_metrics_text=metrics_text,
        )
        return self._complete(prompt)

    # ------------------------------------------------------------------
    # Private: dispatch to provider
    # ------------------------------------------------------------------

    def _complete(self, user_prompt: str) -> str:
        if self._provider == "azure_openai":
            return self._call_azure_openai(user_prompt)
        elif self._provider == "openai":
            return self._call_openai(user_prompt)
        else:
            return self._call_mock(user_prompt)

    def _call_azure_openai(self, user_prompt: str) -> str:
        try:
            from openai import AzureOpenAI  # type: ignore[import]

            client = AzureOpenAI(
                azure_endpoint=self._settings.azure_openai_endpoint,
                api_key=self._settings.azure_openai_api_key,
                api_version=self._settings.azure_openai_api_version,
            )
            response = client.chat.completions.create(
                model=self._settings.azure_openai_deployment,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("Azure OpenAI call failed, falling back to mock: %s", exc)
            return self._call_mock(user_prompt)

    def _call_openai(self, user_prompt: str) -> str:
        try:
            from openai import OpenAI  # type: ignore[import]

            client = OpenAI(api_key=self._settings.openai_api_key)
            response = client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=512,
                temperature=0.3,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("OpenAI call failed, falling back to mock: %s", exc)
            return self._call_mock(user_prompt)

    def _call_mock(self, user_prompt: str) -> str:
        """
        The mock summarizer cannot parse arbitrary prompts directly —
        it is called from higher-level generate_* methods.
        This path is only reached if _complete is called directly, so
        we return a generic placeholder.
        """
        return "(mock response — configure LLM credentials for AI-generated text)"
