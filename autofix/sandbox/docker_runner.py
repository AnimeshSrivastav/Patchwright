from __future__ import annotations

import logging
import os
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from autofix.sandbox.constraints import SandboxConstraints, DEFAULT_CONSTRAINTS

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0


class DockerSandbox:
    """
    Manages a single-use Docker container for running untrusted generated code.
    Non-root, no host mounts, network isolated, CPU/memory bounded.
    """

    def __init__(
        self,
        repo_path: Path,
        image: str = "patchwright-sandbox:latest",
        constraints: SandboxConstraints = DEFAULT_CONSTRAINTS,
        mock: bool = False,
    ) -> None:
        self.repo_path = repo_path
        self.image = image
        self.constraints = constraints
        self.mock = mock
        self._container_id: str | None = None

        if not mock:
            import docker  # type: ignore[import-untyped]
            self._client = docker.from_env()

    def __enter__(self) -> "DockerSandbox":
        if not self.mock:
            self._start()
        return self

    def __exit__(self, *_: object) -> None:
        if not self.mock:
            self._stop()

    def _start(self) -> None:
        import docker  # type: ignore[import-untyped]
        c = self.constraints
        self._container = self._client.containers.run(
            self.image,
            command="sleep infinity",
            detach=True,
            remove=True,
            network_mode=c.network_mode,
            user=c.user,
            cpu_quota=c.cpu_quota,
            cpu_period=c.cpu_period,
            mem_limit=c.mem_limit,
            read_only=False,
            volumes={},              # no host mounts
            environment={},          # no env vars leaking into sandbox
            working_dir="/workspace",
        )
        self._container_id = self._container.id
        # Copy repo into container
        self._copy_repo_to_container()

    def _copy_repo_to_container(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with tarfile.open(tmp_path, "w") as tar:
                tar.add(str(self.repo_path), arcname=".")
            with open(tmp_path, "rb") as f:
                self._container.put_archive("/workspace", f.read())
        finally:
            os.unlink(tmp_path)

    def exec(self, cmd: str, timeout_s: int | None = None) -> ExecResult:
        """Run a shell command inside the sandbox."""
        if self.mock:
            # Return "0" as stdout so numeric checks (wc -l, diff counts) pass correctly
            return ExecResult(stdout="0", stderr="", returncode=0)
        t = timeout_s or self.constraints.timeout_s
        result = self._container.exec_run(
            ["/bin/sh", "-c", cmd],
            demux=True,
            environment={},
        )
        stdout_raw, stderr_raw = result.output or (b"", b"")
        return ExecResult(
            stdout=(stdout_raw or b"").decode(errors="replace"),
            stderr=(stderr_raw or b"").decode(errors="replace"),
            returncode=result.exit_code or 0,
        )

    def read_file(self, path: str) -> str:
        """Read a file from the sandbox."""
        result = self.exec(f"cat {path}")
        return result.stdout

    def write_file(self, path: str, content: str) -> None:
        """Write content to a file in the sandbox (escape single quotes)."""
        escaped = content.replace("'", "'\"'\"'")
        self.exec(f"mkdir -p $(dirname '{path}') && printf '%s' '{escaped}' > '{path}'")

    def _stop(self) -> None:
        try:
            if hasattr(self, "_container"):
                self._container.stop(timeout=5)
        except Exception as e:
            logger.warning("Failed to stop sandbox container: %s", e)
