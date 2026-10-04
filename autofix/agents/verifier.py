from __future__ import annotations

import logging
from dataclasses import dataclass, field

from autofix.sandbox.constraints import SandboxConstraints, DEFAULT_CONSTRAINTS
from autofix.sandbox.docker_runner import DockerSandbox

logger = logging.getLogger(__name__)

_PROTECTED_PATHS = {
    ".github/", "alembic/", "migrations/", "pyproject.toml",
    "requirements.txt", "setup.py", "setup.cfg", "Dockerfile",
    "docker-compose.yml", "tests/conftest.py",
}


@dataclass
class VerifyResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    failure_reason: str = ""

    def __str__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"Verifier: {status}"]
        for check, ok in self.checks.items():
            lines.append(f"  {'[OK]' if ok else '[FAIL]'} {check}")
        if self.failure_reason:
            lines.append(f"  Reason: {self.failure_reason}")
        return "\n".join(lines)


class Verifier:
    """
    Plain Python verifier — NOT an LLM agent.
    All 5 checks must pass; any failure returns passed=False.
    """

    def __init__(
        self,
        max_diff_lines: int = 50,
        max_files_changed: int = 3,
        constraints: SandboxConstraints = DEFAULT_CONSTRAINTS,
    ) -> None:
        self.max_diff_lines = max_diff_lines
        self.max_files_changed = max_files_changed
        self.protected_paths = set(_PROTECTED_PATHS) | set(constraints.protected_paths)

    def verify(
        self,
        sandbox: DockerSandbox,
        test_file_path: str,
        patched_files: list[str],
        diff_lines: int,
        test_failed_before: bool,
    ) -> VerifyResult:
        checks: dict[str, bool] = {}

        # Check 1: Reproducing test failed before patch
        checks["regression_test_failed_before_patch"] = test_failed_before

        # Check 2: Full test suite passes after patch
        suite_result = sandbox.exec("python -m pytest -x -q 2>&1")
        checks["full_suite_green_after_patch"] = suite_result.success
        if not suite_result.success:
            logger.warning("verifier_suite_failed stdout=%s", suite_result.stdout[:500])

        # Check 3: Diff within line limit
        checks[f"diff_within_{self.max_diff_lines}_lines"] = diff_lines <= self.max_diff_lines

        # Check 4: Files changed within limit
        checks[f"files_changed_within_{self.max_files_changed}"] = (
            len(patched_files) <= self.max_files_changed
        )

        # Check 5: No protected paths touched
        protected_touched = [
            f for f in patched_files
            if any(f.startswith(p) or f == p.rstrip("/") for p in self.protected_paths)
        ]
        checks["no_protected_paths_touched"] = len(protected_touched) == 0

        # Check 6: No new dependencies
        dep_result = sandbox.exec(
            "git diff HEAD -- pyproject.toml requirements.txt setup.py setup.cfg 2>/dev/null | wc -l"
        )
        checks["no_new_dependencies"] = dep_result.stdout.strip() == "0"

        passed = all(checks.values())
        failure_reason = ""
        if not passed:
            failures = [k for k, v in checks.items() if not v]
            failure_reason = f"Failed checks: {', '.join(failures)}"
            if protected_touched:
                failure_reason += f". Protected paths touched: {protected_touched}"

        result = VerifyResult(passed=passed, checks=checks, failure_reason=failure_reason)
        logger.info("verifier_result passed=%s checks=%s", passed, checks)
        return result
