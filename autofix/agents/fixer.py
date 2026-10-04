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

_FIXER_PROMPT = """You are a software engineer fixing a bug. Apply the MINIMAL patch.

INCIDENT:
- Error type: {error_type}
- Message: {message}
- Root cause hint: {root_cause_hint}
- Target function: {target_function}

FAILING TEST:
{test_content}

CURRENT FILE CONTENT ({target_file}):
{file_content}

RULES:
- Change as few lines as possible (target: <10 lines changed)
- Do NOT add new dependencies
- Do NOT touch protected paths (.github/, migrations/, pyproject.toml, etc.)
- Do NOT remove or modify existing tests
- Return ONLY a JSON object:
{{
  "file_path": "path/to/file.py",
  "patch_content": "complete new content of the file",
  "root_cause": "one sentence root cause",
  "lines_changed": 5
}}"""


@dataclass
class PatchResult:
    success: bool
    file_path: str
    patch_content: str
    root_cause: str
    lines_changed: int
    error: str = ""


class FixerAgent:
    """
    ADK-powered agent that produces a minimal patch for a failing test.
    Called in a loop (max 3 iterations) from pipeline.py.
    Does NOT decide success — the Verifier does.
    """

    def __init__(self, model: str, mock: bool = False) -> None:
        self.model = model
        self.mock = mock
        self._agent = LlmAgent(
            model=model,
            name="fixer",
            description="Applies the smallest possible patch to fix a failing test.",
            instruction="Return only valid JSON. Never add markdown fences.",
        )

    def fix(
        self,
        incident: Incident,
        sandbox: DockerSandbox,
        test_file_path: str,
        test_content: str,
        target_function: str,
        root_cause_hint: str,
        iteration: int,
    ) -> PatchResult:
        if self.mock:
            return self._mock_patch(incident, target_function)

        # Infer target file from target_function (e.g. "app.routes.get_item" -> "app/routes.py")
        target_file = self._function_to_path(target_function)
        file_content = sandbox.read_file(target_file)

        prompt = _FIXER_PROMPT.format(
            error_type=incident.error_type,
            message=incident.message,
            root_cause_hint=root_cause_hint,
            target_function=target_function,
            test_content=test_content[:1500],
            target_file=target_file,
            file_content=file_content[:3000],
        )
        if iteration > 1:
            prompt += f"\n\nNote: This is attempt {iteration}. Previous patches failed. Try a different approach."

        raw = self._call_llm(prompt)
        try:
            data = self._extract_json(raw)
            return PatchResult(
                success=True,
                file_path=data["file_path"],
                patch_content=data["patch_content"],
                root_cause=data.get("root_cause", ""),
                lines_changed=int(data.get("lines_changed", 0)),
            )
        except Exception as e:
            logger.error("fixer_error incident_id=%s iter=%d error=%s", incident.id, iteration, e)
            return PatchResult(
                success=False, file_path="", patch_content="",
                root_cause="", lines_changed=0, error=str(e),
            )

    def _function_to_path(self, target_function: str) -> str:
        """Convert 'module.submodule.function' to 'module/submodule.py'."""
        parts = target_function.split(".")
        if len(parts) >= 2:
            return "/".join(parts[:-1]) + ".py"
        return target_function + ".py"

    def _call_llm(self, prompt: str) -> str:
        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._agent, app_name="patchwright", session_service=session_service
        )
        session = asyncio.get_event_loop().run_until_complete(
            session_service.create_session(app_name="patchwright", user_id="fixer")
        )
        content = genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])
        text = ""
        for event in runner.run(user_id="fixer", session_id=session.id, new_message=content):
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

    def _mock_patch(self, incident: Incident, target_function: str) -> PatchResult:
        return PatchResult(
            success=True,
            file_path="app/routes.py",
            patch_content="# mock patched content",
            root_cause=f"Mock root cause for {incident.error_type}: {incident.message[:60]}",
            lines_changed=3,
        )
