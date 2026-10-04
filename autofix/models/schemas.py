from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Incident(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    fingerprint: str
    timestamp: datetime
    route: Literal["fixer", "reporter", "ignore"] | None = None
    status_code: int
    error_type: str
    message: str
    stack_trace: str
    redacted_excerpt: str
    occurrence_count: int = 1
    status: Literal[
        "detected", "routed", "ignored", "reported", "fixing", "pr_opened", "failed", "closed"
    ] = "detected"


class RoutingProbabilities(BaseModel):
    model_config = ConfigDict(strict=True)

    client_caused: float = Field(ge=0.0, le=1.0)
    infra_or_upstream: float = Field(ge=0.0, le=1.0)
    trace_in_our_code: float = Field(ge=0.0, le=1.0)
    reproducible_in_test: float = Field(ge=0.0, le=1.0)


class RoutingDecision(BaseModel):
    model_config = ConfigDict(strict=True)

    incident_id: str
    error_class: Literal["user_error", "system_error", "infra", "unknown"]
    next_agent: Literal["fixer", "reporter", "ignore"]
    probabilities: RoutingProbabilities
    confidence: float = Field(ge=0.0, le=1.0)
    suspected_files: list[str] = Field(default_factory=list)
    reasoning: str = Field(max_length=500)
    router_name: str

    @field_validator("reasoning")
    @classmethod
    def reasoning_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reasoning must not be empty")
        return v


class FixOutcome(BaseModel):
    model_config = ConfigDict(strict=True)

    incident_id: str
    reproduced: bool
    root_cause: str
    branch: str
    tests_pass: bool
    regression_test_added: bool
    diff_lines: int
    files_changed: int
    status: Literal["fixed", "cannot_reproduce", "unclear", "failed"]
    iterations_used: int
    reproducing_test_failed_before: bool = False


class CostRecord(BaseModel):
    model_config = ConfigDict(strict=True)

    incident_id: str
    component: str
    tokens_in: int
    tokens_out: int
    usd: float
    wall_seconds: float
