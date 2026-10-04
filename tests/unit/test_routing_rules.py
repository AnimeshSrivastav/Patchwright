import pytest
from datetime import datetime, timezone
from autofix.models.schemas import Incident, RoutingDecision, RoutingProbabilities
from autofix.routing.rules import apply_hard_rules


def make_incident(status_code: int, message: str = "Some error", stack_trace: str = 'File "app/routes.py", line 24, in handler') -> Incident:
    return Incident(
        id="test-id",
        fingerprint="abc123",
        timestamp=datetime.now(timezone.utc),
        status_code=status_code,
        error_type="TestError",
        message=message,
        stack_trace=stack_trace,
        redacted_excerpt="GET /test -> 500",
        occurrence_count=1,
        status="detected",
    )


def make_decision(next_agent: str, confidence: float = 0.8, **prob_kwargs) -> RoutingDecision:
    defaults = dict(client_caused=0.1, infra_or_upstream=0.1, trace_in_our_code=0.9, reproducible_in_test=0.8)
    defaults.update(prob_kwargs)
    return RoutingDecision(
        incident_id="test-id",
        error_class="system_error",
        next_agent=next_agent,
        probabilities=RoutingProbabilities(**defaults),
        confidence=confidence,
        suspected_files=["app/routes.py"],
        reasoning="Test decision",
        router_name="test",
    )


class TestFourxxRule:
    def test_4xx_without_code_trace_becomes_ignore(self):
        inc = make_incident(404)
        dec = make_decision("fixer", client_caused=0.8, trace_in_our_code=0.2)
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "ignore"
        assert "[RULE OVERRIDE]" in result.reasoning

    def test_4xx_with_strong_code_trace_and_low_client_caused_becomes_reporter(self):
        inc = make_incident(422, message="validation rejects valid input")
        dec = make_decision("fixer", client_caused=0.1, trace_in_our_code=0.8)
        result = apply_hard_rules(inc, dec)
        # Should NOT override to ignore since trace_in_our_code > 0.7 and client_caused < 0.2
        # But also should not be fixer — becomes reporter per spec
        assert result.next_agent != "fixer"


class TestInfraRule:
    def test_connection_refused_becomes_reporter(self):
        inc = make_incident(503, message="Connection refused: database is down")
        dec = make_decision("fixer")
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "reporter"

    def test_timeout_becomes_reporter(self):
        inc = make_incident(504, message="upstream API timed out after 30s")
        dec = make_decision("fixer")
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "reporter"

    def test_bad_gateway_becomes_reporter(self):
        # "Bad Gateway" alone (without status code prefix) must also match
        inc = make_incident(502, message="Bad Gateway")
        dec = make_decision("fixer")
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "reporter"

    def test_disk_full_becomes_reporter(self):
        inc = make_incident(503, message="OSError: No space left on device")
        dec = make_decision("fixer")
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "reporter"

    def test_oom_becomes_reporter(self):
        inc = make_incident(500, message="out of memory: OOM killer ran")
        dec = make_decision("fixer")
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "reporter"


class TestConfidenceRule:
    def test_low_confidence_becomes_reporter(self):
        inc = make_incident(500)
        dec = make_decision("fixer", confidence=0.3)
        result = apply_hard_rules(inc, dec, confidence_threshold=0.6)
        assert result.next_agent == "reporter"

    def test_high_confidence_not_overridden(self):
        inc = make_incident(500, stack_trace='File "app/routes.py", line 24, in get_item')
        dec = make_decision("fixer", confidence=0.9)
        result = apply_hard_rules(inc, dec, confidence_threshold=0.6)
        assert result.next_agent == "fixer"  # no override


class TestNoStackTrace:
    def test_5xx_no_stack_trace_becomes_reporter(self):
        inc = make_incident(500, stack_trace="")
        dec = make_decision("fixer", confidence=0.85)
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "reporter"

    def test_5xx_with_stack_trace_not_overridden(self):
        inc = make_incident(500, stack_trace='File "app/routes.py", line 24, in get_item')
        dec = make_decision("fixer", confidence=0.85)
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "fixer"


class TestNoOverride:
    def test_clean_500_fixer_not_overridden(self):
        inc = make_incident(500, stack_trace='File "app/routes.py", line 24, in get_item')
        dec = make_decision("fixer", confidence=0.85)
        result = apply_hard_rules(inc, dec)
        assert result.next_agent == "fixer"
        assert "[RULE OVERRIDE]" not in result.reasoning
