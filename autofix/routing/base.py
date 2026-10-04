from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from autofix.models.schemas import Incident, RoutingDecision


@dataclass
class RepoContext:
    """Relevant context from the target repository passed to the router."""
    repo_path: str
    recent_files: list[str]
    language: str = "python"
    framework: str = "fastapi"


@runtime_checkable
class Router(Protocol):
    """
    All routers must implement this interface.
    Routing and confidence decisions are made here; hard rules in rules.py override the output.
    """

    def route(self, incident: Incident, repo_context: RepoContext) -> RoutingDecision:
        """
        Classify an incident and return a routing decision.
        Must never raise — on failure, return a reporter decision with low confidence.
        """
        ...

    @property
    def name(self) -> str:
        """Unique identifier for this router (used in RoutingDecision.router_name)."""
        ...
