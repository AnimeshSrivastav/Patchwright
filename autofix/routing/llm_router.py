from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from pydantic import ValidationError

from autofix.models.schemas import Incident, RoutingDecision, RoutingProbabilities
from autofix.routing.base import RepoContext

logger = logging.getLogger(__name__)

_ROUTING_PROMPT = """You are a code incident classifier. Analyze the incident below and return a JSON object.

INCIDENT:
- Status code: {status_code}
- Error type: {error_type}
- Message: {message}
- Stack trace:
{stack_trace}

SUSPECTED FILES (from stack trace): {suspected_files}

Return ONLY a JSON object (no markdown, no explanation):
{{
  "error_class": "user_error|system_error|infra|unknown",
  "next_agent": "fixer|reporter|ignore",
  "probabilities": {{
    "client_caused": 0.0,
    "infra_or_upstream": 0.0,
    "trace_in_our_code": 0.0,
    "reproducible_in_test": 0.0
  }},
  "confidence": 0.0,
  "suspected_files": [],
  "reasoning": "max 500 chars explaining your decision"
}}

Rules:
- next_agent=fixer ONLY for clear system errors (500s) with trace in our code
- next_agent=ignore for user errors (4xx caused by client)
- next_agent=reporter for infra failures, unclear cases, or low confidence
- confidence reflects how certain you are about next_agent"""


class LLMRouter:
    """
    Routes incidents using an LLM with structured output.
    Retries once on invalid output; falls back to reporter on second failure.
    Hard rules in rules.py are applied after this router returns.
    """

    name = "llm"

    def __init__(self, model: str, mock: bool = False) -> None:
        self.model = model
        self.mock = mock
        self._agent = LlmAgent(
            model=model,
            name="llm_router",
            description="Classifies incidents for routing.",
            instruction="Return only valid JSON matching the specified schema. No markdown.",
        )

    def route(self, incident: Incident, repo_context: RepoContext) -> RoutingDecision:
        if self.mock:
            return self._mock_decision(incident)

        prompt = _ROUTING_PROMPT.format(
            status_code=incident.status_code,
            error_type=incident.error_type,
            message=incident.message,
            stack_trace=incident.stack_trace[:2000],
            suspected_files=", ".join(repo_context.recent_files[:10]),
        )

        raw = self._call_llm(prompt)
        decision = self._parse_with_retry(raw, incident, prompt)
        logger.info(
            "llm_router_decision",
            incident_id=incident.id,
            next_agent=decision.next_agent,
            confidence=decision.confidence,
            probabilities=decision.probabilities.model_dump(),
        )
        return decision

    def _call_llm(self, prompt: str) -> str:
        import asyncio
        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._agent,
            app_name="patchwright",
            session_service=session_service,
        )
        session = asyncio.get_event_loop().run_until_complete(
            session_service.create_session(app_name="patchwright", user_id="router")
        )
        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)],
        )
        response_text = ""
        for event in runner.run(
            user_id="router",
            session_id=session.id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_text += part.text
        return response_text

    def _parse_with_retry(
        self, raw: str, incident: Incident, original_prompt: str
    ) -> RoutingDecision:
        for attempt in range(2):
            try:
                data = self._extract_json(raw)
                return RoutingDecision(
                    incident_id=incident.id,
                    error_class=data["error_class"],
                    next_agent=data["next_agent"],
                    probabilities=RoutingProbabilities(**data["probabilities"]),
                    confidence=float(data["confidence"]),
                    suspected_files=data.get("suspected_files", []),
                    reasoning=str(data.get("reasoning", ""))[:500],
                    router_name=self.name,
                )
            except (ValidationError, KeyError, ValueError, json.JSONDecodeError) as e:
                logger.warning("llm_router_parse_error attempt=%d error=%s", attempt, e)
                if attempt == 0:
                    # Retry once with a stricter prompt
                    retry_prompt = (
                        f"Your previous response was invalid JSON or had wrong fields.\n"
                        f"Error: {e}\nResponse was: {raw[:200]}\n\n"
                        f"Return ONLY valid JSON:\n{original_prompt[-500:]}"
                    )
                    raw = self._call_llm(retry_prompt)

        # Second failure — fall back to reporter
        logger.error("llm_router_fallback incident_id=%s", incident.id)
        return self._fallback_decision(incident)

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from model output (strip markdown fences if present)."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return json.loads(text)

    def _mock_decision(self, incident: Incident) -> RoutingDecision:
        """Deterministic mock for testing — routes 5xx to fixer, 4xx to ignore."""
        if incident.status_code >= 500:
            next_agent, error_class, confidence = "fixer", "system_error", 0.85
        elif incident.status_code >= 400:
            next_agent, error_class, confidence = "ignore", "user_error", 0.90
        else:
            next_agent, error_class, confidence = "reporter", "unknown", 0.50
        return RoutingDecision(
            incident_id=incident.id,
            error_class=error_class,  # type: ignore[arg-type]
            next_agent=next_agent,  # type: ignore[arg-type]
            probabilities=RoutingProbabilities(
                client_caused=0.1 if next_agent == "fixer" else 0.8,
                infra_or_upstream=0.1,
                trace_in_our_code=0.9 if next_agent == "fixer" else 0.1,
                reproducible_in_test=0.8 if next_agent == "fixer" else 0.2,
            ),
            confidence=confidence,
            suspected_files=[],
            reasoning="[MOCK] Deterministic routing based on status code.",
            router_name=self.name,
        )

    def _fallback_decision(self, incident: Incident) -> RoutingDecision:
        return RoutingDecision(
            incident_id=incident.id,
            error_class="unknown",
            next_agent="reporter",
            probabilities=RoutingProbabilities(
                client_caused=0.5, infra_or_upstream=0.5,
                trace_in_our_code=0.5, reproducible_in_test=0.5,
            ),
            confidence=0.0,
            suspected_files=[],
            reasoning="LLM router failed after 2 attempts; defaulting to reporter.",
            router_name=self.name,
        )
