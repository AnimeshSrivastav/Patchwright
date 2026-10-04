from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from autofix.models.schemas import CostRecord


_tracer: trace.Tracer | None = None
_cost_accumulator: list[CostRecord] = []


def setup_tracing(otlp_endpoint: str = "") -> None:
    """
    Initialize OTel tracing. If otlp_endpoint is provided, export to Langfuse.
    Falls back to no-op if endpoint is empty (e.g. in tests).
    """
    global _tracer
    provider = TracerProvider()

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore[import-untyped]
            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:
            pass  # Tracing is best-effort; never break the pipeline

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("patchwright")


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        setup_tracing()
    return _tracer  # type: ignore[return-value]


@contextmanager
def span(name: str, incident_id: str = "", **attrs: str) -> Generator[trace.Span, None, None]:
    """Context manager for a named OTel span with optional attributes."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if incident_id:
            s.set_attribute("incident_id", incident_id)
        for k, v in attrs.items():
            s.set_attribute(k, v)
        yield s


def record_cost(record: CostRecord) -> None:
    """Accumulate a cost record and attach to current span."""
    _cost_accumulator.append(record)
    current = trace.get_current_span()
    if current and current.is_recording():
        current.set_attribute(f"cost.{record.component}.tokens_in", record.tokens_in)
        current.set_attribute(f"cost.{record.component}.tokens_out", record.tokens_out)
        current.set_attribute(f"cost.{record.component}.usd", record.usd)


def get_incident_cost(incident_id: str) -> float:
    return sum(r.usd for r in _cost_accumulator if r.incident_id == incident_id)


def get_incident_tokens(incident_id: str) -> int:
    return sum(r.tokens_in + r.tokens_out for r in _cost_accumulator if r.incident_id == incident_id)
