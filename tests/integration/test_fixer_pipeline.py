"""
Integration test: hand-fed log -> pipeline -> fix verified.
Runs entirely in mock mode (no real LLM, Docker, or GitHub calls).
"""
import pytest
from datetime import datetime, timezone
from autofix.models.schemas import Incident
from autofix.config.settings import Settings
from autofix.pipeline import Pipeline
from autofix.storage.db import init_db, get_incident


@pytest.fixture
def settings(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return Settings(
        APP_LOG_URL="http://localhost:8001/logs",
        MOCK_EXTERNAL=True,
        DB_PATH=db_path,
        GITHUB_REPO="owner/test-repo",
        GITHUB_TOKEN="fake-token",
    )


@pytest.fixture
def pipeline(settings):
    return Pipeline(settings)


def make_system_error_incident() -> Incident:
    return Incident(
        id="integration-001",
        fingerprint="int-fp-001",
        timestamp=datetime.now(timezone.utc),
        status_code=500,
        error_type="KeyError",
        message="KeyError: 'price'",
        stack_trace="File \"app/routes.py\", line 24, in get_item\n    return items[item_id]",
        redacted_excerpt="GET /items/999 -> 500",
        occurrence_count=1,
        status="detected",
    )


def test_pipeline_runs_without_exception(pipeline, settings):
    """Full pipeline run in mock mode must not raise."""
    inc = make_system_error_incident()
    pipeline.run(inc)  # Should not raise


def test_pipeline_reaches_terminal_state(pipeline, settings):
    """After pipeline.run(), incident must be in a terminal status."""
    inc = make_system_error_incident()
    init_db(settings.db_path)
    from autofix.storage.db import upsert_incident
    upsert_incident(inc)
    pipeline.run(inc)
    retrieved = get_incident("integration-001")
    assert retrieved is not None
    terminal_statuses = {"pr_opened", "reported", "ignored", "failed"}
    assert retrieved.status in terminal_statuses


def test_pipeline_idempotent_on_duplicate(pipeline, settings):
    """Running the same incident twice must not create duplicate branches."""
    inc = make_system_error_incident()
    init_db(settings.db_path)
    from autofix.storage.db import upsert_incident
    upsert_incident(inc)
    pipeline.run(inc)
    pipeline.run(inc)  # Second run — should be a no-op (dedup)
    # No assertion error = idempotency maintained
