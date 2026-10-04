from __future__ import annotations

import re

from autofix.models.schemas import Incident, RoutingDecision, RoutingProbabilities


# Patterns that indicate infra/upstream issues regardless of LLM output
_INFRA_PATTERNS = re.compile(
    r"(connection refused|timeout|timed out|out of memory|OOM|"
    r"bad gateway|service unavailable|gateway timeout|"
    r"no space left on device|disk full|ENOSPC|"
    r"upstream|circuit.?breaker|too many connections)",
    re.IGNORECASE,
)


def apply_hard_rules(
    incident: Incident,
    decision: RoutingDecision,
    confidence_threshold: float = 0.6,
) -> RoutingDecision:
    """
    Override the LLM/router decision with deterministic rules.
    These rules always win. Log every override.
    """
    p = decision.probabilities
    overridden_agent = None
    overridden_reason = None

    # Rule 1: 4xx status codes
    if 400 <= incident.status_code < 500:
        if p.trace_in_our_code > 0.7 and p.client_caused < 0.2:
            # Our validation bug caused a 4xx — route to reporter (never fixer for 4xx)
            overridden_agent = "reporter"
            overridden_reason = f"4xx ({incident.status_code}) traced to our code — reporter, not fixer"
        else:
            # Pure client error — ignore
            overridden_agent = "ignore"
            overridden_reason = f"4xx ({incident.status_code}) with no strong code trace"

    # Rule 2: Infra/upstream patterns
    if _INFRA_PATTERNS.search(incident.message) or _INFRA_PATTERNS.search(incident.stack_trace):
        overridden_agent = "reporter"
        overridden_reason = "infra/upstream pattern detected"

    # Rule 3: No stack trace for a 5xx → cannot reproduce, send to reporter
    if incident.status_code >= 500 and not incident.stack_trace.strip():
        overridden_agent = "reporter"
        overridden_reason = "5xx with no stack trace — cannot reproduce"

    # Rule 4: Low confidence
    if decision.confidence < confidence_threshold:
        overridden_agent = "reporter"
        overridden_reason = f"confidence {decision.confidence:.2f} < threshold {confidence_threshold:.2f}"

    if overridden_agent is None:
        return decision

    return RoutingDecision(
        incident_id=decision.incident_id,
        error_class=decision.error_class,
        next_agent=overridden_agent,  # type: ignore[arg-type]
        probabilities=decision.probabilities,
        confidence=decision.confidence,
        suspected_files=decision.suspected_files,
        reasoning=f"[RULE OVERRIDE] {overridden_reason}. Original: {decision.reasoning[:200]}",
        router_name=decision.router_name,
    )


def is_duplicate(fingerprint: str, existing_fingerprints: set[str]) -> bool:
    return fingerprint in existing_fingerprints
