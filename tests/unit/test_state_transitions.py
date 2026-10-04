import pytest
import tempfile
import os
import shutil
from datetime import datetime, timezone
from autofix.models.schemas import Incident
from autofix.storage.db import (
    init_db, upsert_incident, transition, get_incident,
    get_open_by_fingerprint, increment_occurrence
)


@pytest.fixture
def db():
    # Use tempfile directly — avoids pytest-asyncio/tmp_path permission issue on Windows
    tmpdir = tempfile.mkdtemp(prefix="pw_test_")
    db_path = os.path.join(tmpdir, "test.db")
    init_db(db_path)
    yield db_path
    shutil.rmtree(tmpdir, ignore_errors=True)


def make_incident(id: str, fingerprint: str = "fp001") -> Incident:
    return Incident(
        id=id,
        fingerprint=fingerprint,
        timestamp=datetime.now(timezone.utc),
        status_code=500,
        error_type="KeyError",
        message="KeyError: 'price'",
        stack_trace="File app/routes.py line 24",
        redacted_excerpt="GET /items -> 500",
        occurrence_count=1,
        status="detected",
    )


def test_upsert_and_retrieve(db):
    inc = make_incident("inc-001")
    upsert_incident(inc)
    retrieved = get_incident("inc-001")
    assert retrieved is not None
    assert retrieved.id == "inc-001"
    assert retrieved.status == "detected"


def test_transition_updates_status(db):
    inc = make_incident("inc-002")
    upsert_incident(inc)
    transition("inc-002", "routed")
    retrieved = get_incident("inc-002")
    assert retrieved.status == "routed"


def test_full_lifecycle(db):
    inc = make_incident("inc-003")
    upsert_incident(inc)

    for status in ["routed", "fixing", "pr_opened", "closed"]:
        transition("inc-003", status)
        retrieved = get_incident("inc-003")
        assert retrieved.status == status


def test_get_open_by_fingerprint(db):
    inc = make_incident("inc-004", fingerprint="fp_open")
    upsert_incident(inc)
    found = get_open_by_fingerprint("fp_open")
    assert found is not None
    assert found.id == "inc-004"


def test_closed_incident_not_found_as_open(db):
    inc = make_incident("inc-005", fingerprint="fp_closed")
    upsert_incident(inc)
    transition("inc-005", "closed")
    found = get_open_by_fingerprint("fp_closed")
    assert found is None


def test_increment_occurrence(db):
    inc = make_incident("inc-006", fingerprint="fp_dup")
    upsert_incident(inc)
    increment_occurrence("inc-006")
    increment_occurrence("inc-006")
    retrieved = get_incident("inc-006")
    assert retrieved.occurrence_count == 3


def test_reprocessing_incident_no_duplicate(db):
    """Re-inserting the same incident must not create a new row."""
    inc = make_incident("inc-007")
    upsert_incident(inc)
    upsert_incident(inc)  # second call — idempotent
    # Still only one incident
    retrieved = get_incident("inc-007")
    assert retrieved is not None
    assert retrieved.occurrence_count == 1
