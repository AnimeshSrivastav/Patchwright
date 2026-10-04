"""
Router contract test — any Router implementation must pass all tests in this file.
Tests both LLMRouter (mock mode) and JevRouter (raises NotImplementedError — expected).
"""
import pytest
from datetime import datetime, timezone
from autofix.models.schemas import Incident, RoutingDecision
from autofix.routing.base import Router, RepoContext
from autofix.routing.llm_router import LLMRouter
from autofix.routing.jev_router import JevRouter


def make_incident(status_code: int = 500) -> Incident:
    return Incident(
        id="contract-test-id",
        fingerprint="contract-fp",
        timestamp=datetime.now(timezone.utc),
        status_code=status_code,
        error_type="KeyError",
        message="KeyError: 'price'",
        stack_trace="File app/routes.py line 24\n    return items[item_id]",
        redacted_excerpt="GET /items -> 500",
        occurrence_count=1,
        status="detected",
    )


REPO_CTX = RepoContext(repo_path=".", recent_files=["app/routes.py"])


class RouterContractTests:
    """Base class — subclass and set self.router to test any Router implementation."""

    router: Router

    def test_implements_router_protocol(self):
        assert isinstance(self.router, Router)

    def test_has_name_property(self):
        assert isinstance(self.router.name, str)
        assert len(self.router.name) > 0

    def test_route_returns_routing_decision(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert isinstance(result, RoutingDecision)

    def test_next_agent_is_valid_value(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert result.next_agent in ("fixer", "reporter", "ignore")

    def test_error_class_is_valid_value(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert result.error_class in ("user_error", "system_error", "infra", "unknown")

    def test_probabilities_in_range(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        p = result.probabilities
        for val in [p.client_caused, p.infra_or_upstream, p.trace_in_our_code, p.reproducible_in_test]:
            assert 0.0 <= val <= 1.0

    def test_confidence_in_range(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert 0.0 <= result.confidence <= 1.0

    def test_reasoning_not_empty(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert len(result.reasoning) > 0

    def test_reasoning_max_500_chars(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert len(result.reasoning) <= 500

    def test_router_name_in_decision(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert result.router_name == self.router.name

    def test_incident_id_in_decision(self):
        inc = make_incident(500)
        result = self.router.route(inc, REPO_CTX)
        assert result.incident_id == inc.id


class TestLLMRouterContract(RouterContractTests):
    @pytest.fixture(autouse=True)
    def setup(self):
        self.router = LLMRouter(model="gemini-2.0-flash", mock=True)


class TestJevRouterContract:
    """JevRouter contract — it must raise NotImplementedError with a clear message."""

    def setup_method(self):
        self.router = JevRouter()

    def test_implements_router_protocol(self):
        assert isinstance(self.router, Router)

    def test_has_name_property(self):
        assert self.router.name == "jev"

    def test_raises_not_implemented_with_message(self):
        inc = make_incident(500)
        with pytest.raises(NotImplementedError) as exc_info:
            self.router.route(inc, REPO_CTX)
        error_msg = str(exc_info.value)
        assert "JevRouter" in error_msg
        assert "ROUTER=llm" in error_msg
