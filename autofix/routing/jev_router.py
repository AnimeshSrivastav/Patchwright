from __future__ import annotations

from autofix.models.schemas import Incident, RoutingDecision
from autofix.routing.base import RepoContext


class JevRouter:
    """
    Stub implementation of the Router protocol for the Jev routing system.

    This stub exists to:
    1. Satisfy the Router contract (contract test in tests/unit/test_router_contract.py)
    2. Document the expected interface once Jev access becomes available
    3. Ensure the config system can reference ROUTER=jev without crashing at startup

    DO NOT guess or implement Jev's actual API — wait for official docs.
    """

    name = "jev"

    def route(self, incident: Incident, repo_context: RepoContext) -> RoutingDecision:
        raise NotImplementedError(
            "JevRouter: Jev API access is not yet available. "
            "Set ROUTER=llm in your environment to use the LLMRouter instead. "
            "When Jev credentials and documentation are available, implement this class "
            "following the Router protocol in autofix/routing/base.py."
        )
