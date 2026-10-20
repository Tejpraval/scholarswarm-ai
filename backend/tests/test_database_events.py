"""Tests for persisting agent events in the SSE response shape."""
import os

from app.models.workflow import AgentEvent, AgentStatus
from app.services import database


def test_agent_event_round_trip_keeps_details_errors_and_timing(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "events.sqlite"))
    database.init_db()
    event = AgentEvent(
        run_id="run-1",
        agent_name="scholarship_researcher",
        status=AgentStatus.RETRYING,
        message="Search query failed; continuing.",
        details={"query": "masters scholarship", "result_urls": ["https://provider.example"]},
        error="TimeoutException",
        retry_count=1,
        duration_ms=125,
    )

    database.save_events("run-1", [event])
    saved = database.get_events_for_run("run-1")[0]

    assert saved["details"] == event.details
    assert saved["error"] == "TimeoutException"
    assert saved["retry_count"] == 1
    assert saved["duration_ms"] == 125
    assert saved["timestamp"] == event.timestamp.isoformat()


def test_startup_recovery_only_fails_runs_owned_by_dead_process(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "runs.sqlite"))
    database.init_db()
    database.save_workflow_run(
        {"id": "live-run", "process_id": os.getpid()},
        run_id="live-run", student_id="student-1", status="running",
    )
    database.save_workflow_run(
        {"id": "stale-run", "process_id": 999999},
        run_id="stale-run", student_id="student-2", status="running",
    )

    monkeypatch.setattr(
        database, "_process_is_alive", lambda pid: pid == os.getpid()
    )

    assert database.mark_interrupted_runs_failed() == 1
    conn = database.get_connection()
    try:
        statuses = {
            row["id"]: row["status"]
            for row in conn.execute("SELECT id, status FROM workflow_runs")
        }
    finally:
        conn.close()
    assert statuses == {"live-run": "running", "stale-run": "failed"}
