from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from autofix.models.schemas import Incident
from autofix.sandbox.docker_runner import DockerSandbox

logger = logging.getLogger(__name__)

_REPRODUCER_PROMPT = """You are a test engineer. Write a minimal pytest test that reproduces the following bug.

INCIDENT:
- Error type: {error_type}
- Message: {message}
- Stack trace:
{stack_trace}
- Suspected files: {suspected_files}

REQUIREMENTS:
1. The test must FAIL (raise an exception matching the error) on the current code.
2. The test must use pytest conventions.
3. Import only from the project (no new dependencies).
4. Test function name: test_regression_{incident_id_short}
5. Keep it minimal — test only the failing behavior.

Return ONLY a JSON object:
{{
  "test_file_path": "tests/test_regression_{incident_id_short}.py",
  "test_content": "full test file content as string",
  "target_function": "module.function that needs fixing",
  "expected_fix_hint": "brief description of what the fix should do"
}}"""


@dataclass
class ReproducerResult:
    success: bool
    test_file_path: str
    test_content: str
    target_function: str
    expected_fix_hint: str
    error: str = ""


class ReproducerAgent:
    """
    ADK-powered agent that writes a failing pytest test for an incident.
    If no matching failing test can be produced, returns success=False.
    """

    def __init__(self, model: str, mock: bool = False) -> None:
        self.model = model
        self.mock = mock
        self._agent = LlmAgent(
            model=model,
            name="reproducer",
            description="Writes a minimal failing pytest test for an incident.",
            instruction="Return only valid JSON. Never add markdown fences.",
        )

    def reproduce(
        self, incident: Incident, sandbox: DockerSandbox, suspected_files: list[str]
    ) -> ReproducerResult:
        if self.mock:
            return self._mock_result(incident)

        prompt = _REPRODUCER_PROMPT.format(
            error_type=incident.error_type,
            message=incident.message,
            stack_trace=incident.stack_trace[:3000],
            suspected_files=", ".join(suspected_files[:5]),
            incident_id_short=incident.id[:8],
        )

        raw = self._call_llm(prompt)
        try:
            data = self._extract_json(raw)
            test_path = data["test_file_path"]
            test_content = data["test_content"]

            # Write the test to sandbox and run it
            sandbox.write_file(test_path, test_content)
            result = sandbox.exec(f"python -m pytest {test_path} -x -q 2>&1")

            # The test must FAIL to confirm reproduction
            if result.returncode == 0:
                logger.warning(
                    "reproducer_test_passed_unexpectedly incident_id=%s", incident.id
                )
                return ReproducerResult(
                    success=False,
                    test_file_path=test_path,
                    test_content=test_content,
                    target_function=data.get("target_function", ""),
                    expected_fix_hint=data.get("expected_fix_hint", ""),
                    error="Test passed before fix — cannot confirm reproduction.",
                )

            logger.info("reproducer_success incident_id=%s test=%s", incident.id, test_path)
            return ReproducerResult(
                success=True,
                test_file_path=test_path,
                test_content=test_content,
                target_function=data.get("target_function", ""),
                expected_fix_hint=data.get("expected_fix_hint", ""),
            )

        except Exception as e:
            logger.error("reproducer_error incident_id=%s error=%s", incident.id, e)
            return ReproducerResult(
                success=False,
                test_file_path="",
                test_content="",
                target_function="",
                expected_fix_hint="",
                error=str(e),
            )

    def _call_llm(self, prompt: str) -> str:
        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._agent,
            app_name="patchwright",
            session_service=session_service,
        )
        session = asyncio.get_event_loop().run_until_complete(
            session_service.create_session(app_name="patchwright", user_id="reproducer")
        )
        content = genai_types.Content(
            role="user", parts=[genai_types.Part(text=prompt)]
        )
        text = ""
        for event in runner.run(user_id="reproducer", session_id=session.id, new_message=content):
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

    def _mock_result(self, incident: Incident) -> ReproducerResult:
        short = incident.id[:8]
        test_content = f"""import pytest

def test_regression_{short}():
    # Mock reproduction test for incident {incident.id}
    # This test is intentionally failing to simulate bug reproduction
    raise {incident.error_type}("Mock reproduction: {incident.message[:80]}")
"""
        return ReproducerResult(
            success=True,
            test_file_path=f"tests/test_regression_{short}.py",
            test_content=test_content,
            target_function="mock.target_function",
            expected_fix_hint="Mock fix hint.",
        )
