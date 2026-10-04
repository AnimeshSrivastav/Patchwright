from __future__ import annotations

import asyncio
import logging

from autofix.config.settings import Settings
from autofix.observability.logging import configure_logging
from autofix.observability.tracing import setup_tracing
from autofix.pipeline import Pipeline
from autofix.monitor.log_poller import LogPoller
from autofix.storage.db import init_db, get_open_by_fingerprint, upsert_incident, increment_occurrence


def main() -> None:
    settings = Settings()
    configure_logging()
    setup_tracing(otlp_endpoint=settings.otel_endpoint)
    init_db(settings.db_path)

    pipeline = Pipeline(settings)

    def handle_incident(incident) -> None:
        # Dedup at the handler level
        existing = get_open_by_fingerprint(incident.fingerprint)
        if existing and existing.id != incident.id:
            increment_occurrence(existing.id)
            return
        upsert_incident(incident)
        pipeline.run(incident)

    poller = LogPoller(
        app_log_url=settings.app_log_url,
        poll_interval_s=settings.poll_interval_s,
        on_new_incident=handle_incident,
    )

    logging.getLogger(__name__).info(
        "patchwright_starting url=%s", settings.app_log_url
    )
    asyncio.run(poller.start())


if __name__ == "__main__":
    main()
