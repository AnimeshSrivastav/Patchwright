from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """
    Configure structlog for JSON output.
    Every log line will include incident_id, trace_id, component via bound context.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(level.upper()),
    )


def bind_incident(incident_id: str, trace_id: str, component: str) -> None:
    """Bind incident context to all subsequent log calls in this async context."""
    structlog.contextvars.bind_contextvars(
        incident_id=incident_id,
        trace_id=trace_id,
        component=component,
    )


def clear_incident() -> None:
    structlog.contextvars.clear_contextvars()


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger().bind(component=component)
