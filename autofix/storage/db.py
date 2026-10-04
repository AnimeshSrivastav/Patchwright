from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from autofix.models.schemas import Incident

_DB_PATH: str = "./patchwright.db"


def init_db(path: str = "./patchwright.db") -> None:
    global _DB_PATH
    _DB_PATH = path
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                route TEXT,
                status_code INTEGER NOT NULL,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                stack_trace TEXT NOT NULL,
                redacted_excerpt TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'detected',
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_fingerprint_open
                ON incidents (fingerprint)
                WHERE status NOT IN ('ignored', 'reported', 'closed', 'failed');

            CREATE TABLE IF NOT EXISTS cost_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                component TEXT NOT NULL,
                tokens_in INTEGER NOT NULL,
                tokens_out INTEGER NOT NULL,
                usd REAL NOT NULL,
                wall_seconds REAL NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
        """)


@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_incident(inc: Incident) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO incidents
                (id, fingerprint, timestamp, route, status_code, error_type, message,
                 stack_trace, redacted_excerpt, occurrence_count, status, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                occurrence_count = excluded.occurrence_count,
                status = excluded.status,
                route = excluded.route,
                updated_at = excluded.updated_at
            """,
            (
                inc.id, inc.fingerprint, inc.timestamp.isoformat(),
                inc.route, inc.status_code, inc.error_type, inc.message,
                inc.stack_trace, inc.redacted_excerpt, inc.occurrence_count,
                inc.status, now,
            ),
        )


def get_open_by_fingerprint(fingerprint: str) -> Incident | None:
    with _connect() as conn:
        row = conn.execute(
            """SELECT * FROM incidents WHERE fingerprint = ?
               AND status NOT IN ('ignored','reported','closed','failed')
               LIMIT 1""",
            (fingerprint,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_incident(row)


def get_incident(incident_id: str) -> Incident | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
    return _row_to_incident(row) if row else None


def increment_occurrence(incident_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE incidents SET occurrence_count = occurrence_count + 1, updated_at = ? WHERE id = ?",
            (now, incident_id),
        )


def transition(incident_id: str, new_status: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        old = conn.execute(
            "SELECT status FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        old_status = old["status"] if old else None
        conn.execute(
            "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, incident_id),
        )
        conn.execute(
            "INSERT INTO state_transitions (incident_id, from_status, to_status, occurred_at) VALUES (?,?,?,?)",
            (incident_id, old_status, new_status, now),
        )


def _row_to_incident(row: sqlite3.Row) -> Incident:
    return Incident(
        id=row["id"],
        fingerprint=row["fingerprint"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        route=row["route"],
        status_code=row["status_code"],
        error_type=row["error_type"],
        message=row["message"],
        stack_trace=row["stack_trace"],
        redacted_excerpt=row["redacted_excerpt"],
        occurrence_count=row["occurrence_count"],
        status=row["status"],
    )
