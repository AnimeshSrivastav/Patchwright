from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxConstraints:
    cpu_quota: int = 100_000   # microseconds per cpu_period (100ms) = 1 CPU
    cpu_period: int = 100_000
    mem_limit: str = "512m"
    timeout_s: int = 120
    network_mode: str = "none"  # no network access inside sandbox
    user: str = "nobody"        # non-root

    # Protected paths — the fixer must never touch these
    protected_paths: tuple[str, ...] = (
        ".github/",
        "alembic/",
        "migrations/",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "Dockerfile",
        "docker-compose.yml",
        "tests/conftest.py",
    )


DEFAULT_CONSTRAINTS = SandboxConstraints()
