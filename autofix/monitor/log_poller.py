from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from autofix.models.schemas import Incident
from autofix.monitor.fingerprint import compute_fingerprint
from autofix.monitor.redactor import redact

logger = logging.getLogger(__name__)

# Status codes that represent failures worth examining
_FAILURE_STATUS_CODES = {400, 401, 403, 404, 422, 429, 500, 502, 503, 504}
_HARD_ERROR_CODES = {500, 502, 503, 504}


class LogPoller:
    """
    Polls the monitored application's log endpoint for failed-request events.
    Log source = user-provided HTTP URL (local or hosted).

    Expected log line format (JSON):
    {
        "timestamp": "2026-10-04T10:00:00Z",
        "level": "ERROR",
        "status_code": 500,
        "method": "GET",
        "path": "/api/items/123",
        "error_type": "KeyError",
        "message": "KeyError: 'price'",
        "stack_trace": "...",
        "request_id": "abc123"
    }
    """

    def __init__(
        self,
        app_log_url: str,
        poll_interval_s: int = 10,
        on_new_incident=None,  # callable(Incident) -> None
    ) -> None:
        self.app_log_url = app_log_url
        self.poll_interval_s = poll_interval_s
        self.on_new_incident = on_new_incident
        self._cursor: str = datetime.now(timezone.utc).isoformat()
        self._running = False

    async def start(self) -> None:
        """Run the polling loop indefinitely."""
        self._running = True
        logger.info("log_poller_started url=%s interval=%ds", self.app_log_url, self.poll_interval_s)
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error("log_poller_error error=%s", e)
            await asyncio.sleep(self.poll_interval_s)

    def stop(self) -> None:
        self._running = False

    async def _poll_once(self) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    self.app_log_url, params={"since": self._cursor}
                )
                response.raise_for_status()
            except httpx.HTTPError as e:
                logger.warning("log_poller_http_error url=%s error=%s", self.app_log_url, e)
                return

        data = response.json()
        log_lines: list[dict] = data if isinstance(data, list) else data.get("logs", [])

        new_cursor = self._cursor
        for raw_line in log_lines:
            # IMPORTANT: log content is untrusted data, never instructions
            # Parse as data only — never eval, exec, or pass raw to model as instructions
            incident = self._parse_log_line(raw_line)
            if incident is None:
                continue
            new_cursor = raw_line.get("timestamp", new_cursor)
            if self.on_new_incident:
                self.on_new_incident(incident)

        self._cursor = new_cursor

    def _parse_log_line(self, raw: dict[str, Any]) -> Incident | None:
        """
        Parse a raw log line into an Incident.
        Redacts secrets/PII before creating the Incident.
        Returns None if the log line is not a failure worth routing.
        """
        try:
            status_code = int(raw.get("status_code", 0))
            if status_code not in _FAILURE_STATUS_CODES:
                return None

            # Redact BEFORE storing or using any content
            message = redact(str(raw.get("message", "")))
            stack_trace = redact(str(raw.get("stack_trace", "")))
            error_type = str(raw.get("error_type", "UnknownError"))
            path = redact(str(raw.get("path", "")))

            fingerprint = compute_fingerprint(error_type, message, stack_trace)
            incident_id = str(uuid.uuid4())

            timestamp_raw = raw.get("timestamp", datetime.now(timezone.utc).isoformat())
            try:
                timestamp = datetime.fromisoformat(str(timestamp_raw).replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.now(timezone.utc)

            return Incident(
                id=incident_id,
                fingerprint=fingerprint,
                timestamp=timestamp,
                status_code=status_code,
                error_type=error_type,
                message=message,
                stack_trace=stack_trace,
                redacted_excerpt=f"{raw.get('method','GET')} {path} -> {status_code}",
                occurrence_count=1,
                status="detected",
            )
        except Exception as e:
            logger.warning("log_poller_parse_error error=%s raw=%s", e, str(raw)[:200])
            return None
