from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from autofix.models.schemas import FixOutcome, Incident, RoutingDecision

logger = logging.getLogger(__name__)

_REPORTER_PROMPT = """You are a software engineer writing an incident report. Be concise and factual.

INCIDENT:
- ID: {incident_id}
- Error: {error_type}: {message}
- Status code: {status_code}
- Route decision: {next_agent} (reason: {routing_reason})
- Suspected files: {suspected_files}
- Fix outcome: {fix_status}

Write a short incident report. Return ONLY JSON:
{{
  "summary": "1-2 sentence summary of what failed",
  "error_class": "brief classification",
  "why_not_fixed": "reason no fix was attempted or fix failed",
  "suspected_files": ["list", "of", "files"],
  "next_steps": "suggested action for a human engineer"
}}"""


class ReporterAgent:
    """
    ADK-powered agent that produces short incident reports.
    Used when: routing = reporter, or fix pipeline failed/cannot_reproduce.
    Does NOT create GitHub issues (optional extension).
    """

    def __init__(self, model: str, mock: bool = False) -> None:
        self.model = model
        self.mock = mock
        self._agent = LlmAgent(
            model=model,
            name="reporter",
            description="Writes concise incident reports.",
            instruction="Return only valid JSON. Be factual and brief.",
        )

    def report(
        self,
        incident: Incident,
        routing: RoutingDecision,
        fix_outcome: FixOutcome | None = None,
    ) -> dict[str, str]:
        if self.mock:
            return self._mock_report(incident, routing)

        prompt = _REPORTER_PROMPT.format(
            incident_id=incident.id,
            error_type=incident.error_type,
            message=incident.message[:500],
            status_code=incident.status_code,
            next_agent=routing.next_agent,
            routing_reason=routing.reasoning[:200],
            suspected_files=", ".join(routing.suspected_files[:5]),
            fix_status=fix_outcome.status if fix_outcome else "not_attempted",
        )

        raw = self._call_llm(prompt)
        try:
            data = self._extract_json(raw)
            logger.info("reporter_done incident_id=%s", incident.id)
            return data
        except Exception as e:
            logger.error("reporter_error incident_id=%s error=%s", incident.id, e)
            return {
                "summary": f"{incident.error_type}: {incident.message[:100]}",
                "error_class": routing.error_class,
                "why_not_fixed": routing.reasoning,
                "suspected_files": routing.suspected_files,
                "next_steps": "Manual investigation required.",
            }

    def _call_llm(self, prompt: str) -> str:
        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._agent, app_name="patchwright", session_service=session_service
        )
        session = asyncio.get_event_loop().run_until_complete(
            session_service.create_session(app_name="patchwright", user_id="reporter")
        )
        content = genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
        text = ""
        for event in runner.run(user_id="reporter", session_id=session.id, new_message=content):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text
        return text

    def _extract_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return json.loads(text)

    def _mock_report(self, incident: Incident, routing: RoutingDecision) -> dict[str, str]:
        return {
            "summary": f"[MOCK] {incident.error_type} at status {incident.status_code}.",
            "error_class": routing.error_class,
            "why_not_fixed": routing.reasoning,
            "suspected_files": routing.suspected_files,
            "next_steps": "Review the stack trace and suspected files.",
        }
