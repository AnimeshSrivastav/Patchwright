"""
Quick incident status viewer.

Usage:
    uv run python -m autofix.status           # show all incidents
    uv run python -m autofix.status --tail    # show last 10
    uv run python -m autofix.status --id <id> # show one incident in detail
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


_STATUS_EMOJI = {
    "detected":   "[ ]",
    "routed":     "[>]",
    "ignored":    "[~]",
    "reported":   "[!]",
    "fixing":     "[*]",
    "pr_opened":  "[PR]",
    "failed":     "[X]",
    "closed":     "[v]",
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def show_all(db_path: str, tail: int | None = None) -> None:
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT id, status, error_type, message, occurrence_count, updated_at "
        "FROM incidents ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()

    if not rows:
        print("No incidents recorded yet.")
        return

    if tail:
        rows = rows[:tail]

    print(f"\n{'STATUS':<8} {'ID':<10} {'ERROR TYPE':<22} {'MESSAGE':<50} {'OCCUR':<6} UPDATED")
    print("-" * 115)
    for r in rows:
        icon = _STATUS_EMOJI.get(r["status"], "[?]")
        short_id = r["id"][:8]
        msg = r["message"][:48].replace("\n", " ")
        print(f"{icon:<8} {short_id:<10} {r['error_type']:<22} {msg:<50} {r['occurrence_count']:<6} {r['updated_at'][:19]}")
    print()


def show_one(db_path: str, incident_id: str) -> None:
    conn = _connect(db_path)

    # Accept short IDs (first 8 chars)
    if len(incident_id) < 36:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id LIKE ?", (f"{incident_id}%",)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()

    if not row:
        print(f"No incident found matching '{incident_id}'")
        conn.close()
        return

    transitions = conn.execute(
        "SELECT from_status, to_status, occurred_at FROM state_transitions "
        "WHERE incident_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    conn.close()

    icon = _STATUS_EMOJI.get(row["status"], "[?]")
    print(f"\n{'='*60}")
    print(f"  {icon}  Incident {row['id']}")
    print(f"{'='*60}")
    print(f"  Status:      {row['status']}")
    print(f"  Route:       {row['route'] or 'not routed yet'}")
    print(f"  Error type:  {row['error_type']}")
    print(f"  Status code: {row['status_code']}")
    print(f"  Occurrences: {row['occurrence_count']}")
    print(f"  Timestamp:   {row['timestamp']}")
    print(f"  Updated:     {row['updated_at']}")
    print(f"\n  Message:\n    {row['message']}")
    print(f"\n  Redacted excerpt:\n    {row['redacted_excerpt']}")
    if row["stack_trace"]:
        print(f"\n  Stack trace (first 5 lines):")
        for line in row["stack_trace"].splitlines()[:5]:
            print(f"    {line}")

    if transitions:
        print(f"\n  Lifecycle:")
        for t in transitions:
            frm = t["from_status"] or "start"
            print(f"    {frm:>12}  ->  {t['to_status']:<12}  at {t['occurred_at'][:19]}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Patchwright incident status viewer")
    parser.add_argument("--db", default="./patchwright.db", help="Path to SQLite DB")
    parser.add_argument("--tail", type=int, default=None, help="Show last N incidents")
    parser.add_argument("--id", dest="incident_id", default=None, help="Show one incident (full or short ID)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        print("Run `python -m autofix` first to start the monitor.")
        sys.exit(1)

    if args.incident_id:
        show_one(args.db, args.incident_id)
    else:
        show_all(args.db, tail=args.tail)


if __name__ == "__main__":
    main()
