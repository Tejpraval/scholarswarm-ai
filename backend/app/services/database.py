"""SQLite database service for persisting workflow runs and results."""
from __future__ import annotations
import errno
import json
import logging
import os
import sqlite3
import ctypes
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "scholarswarm.db")


def _process_is_alive(pid: int) -> bool:
    """Check a process without signaling it, including on Windows."""
    pid = int(pid)
    if pid == os.getpid():
        return True
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == 5  # access denied still means it exists
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError as exc:
        return exc.errno == errno.EPERM


class _DatetimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime, date, and Enum objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def _dumps(obj) -> str:
    """Serialize to JSON, handling datetimes and enums."""
    return json.dumps(obj, cls=_DatetimeEncoder)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS student_profiles (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL,
            status TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scholarships (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS eligibility_assessments (
            id TEXT PRIMARY KEY,
            scholarship_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS match_results (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            scholarship_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sop_drafts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            scholarship_id TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_events (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            data TEXT,
            created_at TEXT NOT NULL
        );
        """)
        conn.commit()
        logger.info(f"Database initialized at {DB_PATH}")
    finally:
        conn.close()


def save_student_profile(profile) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO student_profiles (id, data, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (profile.id, profile.model_dump_json(), now, now)
        )
        conn.commit()
    finally:
        conn.close()


def get_student_profile(profile_id: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data FROM student_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None
    finally:
        conn.close()


def save_workflow_run(run_data: Dict, run_id: str, student_id: str, status: str) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT created_at FROM workflow_runs WHERE id = ?", (run_id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """INSERT OR REPLACE INTO workflow_runs (id, student_id, status, data, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, student_id, status, _dumps(run_data), created_at, now)
        )
        conn.commit()
    finally:
        conn.close()


def get_workflow_run(run_id: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data FROM workflow_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None
    finally:
        conn.close()


def mark_interrupted_runs_failed() -> int:
    """Mark runs abandoned by a dead server process as failed.

    Multiple local app instances and TestClient startups can share SQLite.
    Leave runs alone while the process that owns them is still alive.
    """
    message = "Backend restarted before this workflow finished. Please retry the run."

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, data FROM workflow_runs WHERE status IN ('queued', 'running')"
        ).fetchall()
        now = datetime.utcnow().isoformat()
        interrupted = 0
        for row in rows:
            data = json.loads(row["data"] or "{}")
            process_id = data.get("process_id")
            if process_id and _process_is_alive(process_id):
                continue
            data.update({
                "id": row["id"],
                "status": "failed",
                "error": message,
                "workflow_error": message,
                "completed_at": now,
            })
            conn.execute(
                "UPDATE workflow_runs SET status = 'failed', data = ?, updated_at = ? WHERE id = ?",
                (_dumps(data), now, row["id"]),
            )
            interrupted += 1
        conn.commit()
        return interrupted
    finally:
        conn.close()


def save_scholarships(run_id: str, scholarships: List) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        for s in scholarships:
            conn.execute(
                """INSERT OR REPLACE INTO scholarships (id, run_id, data, created_at)
                   VALUES (?, ?, ?, ?)""",
                (s.id, run_id, s.model_dump_json(), now)
            )
        conn.commit()
    finally:
        conn.close()


def get_scholarships_for_run(run_id: str) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT data FROM scholarships WHERE run_id = ?", (run_id,)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]
    finally:
        conn.close()


def save_eligibility_assessments(run_id: str, assessments: List) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        for a in assessments:
            conn.execute(
                """INSERT OR REPLACE INTO eligibility_assessments
                   (id, scholarship_id, student_id, run_id, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (a.id, a.scholarship_id, a.student_id, run_id, a.model_dump_json(), now)
            )
        conn.commit()
    finally:
        conn.close()


def get_eligibility_for_scholarship(run_id: str, scholarship_id: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT data FROM eligibility_assessments
               WHERE run_id = ? AND scholarship_id = ?""",
            (run_id, scholarship_id)
        ).fetchone()
        return json.loads(row["data"]) if row else None
    finally:
        conn.close()


def save_match_results(run_id: str, matches: List) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        for m in matches:
            conn.execute(
                """INSERT OR REPLACE INTO match_results
                   (id, run_id, scholarship_id, student_id, rank, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (m.id, run_id, m.scholarship_id, m.student_id, m.rank, m.model_dump_json(), now)
            )
        conn.commit()
    finally:
        conn.close()


def get_match_results_for_run(run_id: str) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT data FROM match_results WHERE run_id = ? ORDER BY rank ASC",
            (run_id,)
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]
    finally:
        conn.close()


def save_sop_draft(draft) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO sop_drafts
               (id, run_id, student_id, scholarship_id, data, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (draft.id, draft.run_id, draft.student_id, draft.scholarship_id, draft.model_dump_json(), now)
        )
        conn.commit()
    finally:
        conn.close()


def get_sop_draft(run_id: str) -> Optional[Dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT data FROM sop_drafts WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            (run_id,)
        ).fetchone()
        return json.loads(row["data"]) if row else None
    finally:
        conn.close()


def save_events(run_id: str, events: List) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    try:
        for ev in events:
            conn.execute(
                """INSERT OR IGNORE INTO agent_events
                   (id, run_id, agent_name, status, message, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ev.id, ev.run_id, ev.agent_name, ev.status.value,
                    ev.message,
                    json.dumps({
                        "details": ev.details,
                        "error": ev.error,
                        "retry_count": ev.retry_count,
                        "duration_ms": ev.duration_ms,
                    }),
                    ev.timestamp.isoformat()
                )
            )
        conn.commit()
    finally:
        conn.close()


def get_events_for_run(run_id: str) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_events WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,)
        ).fetchall()
        events = []
        for row in rows:
            data = dict(row)
            try:
                payload = json.loads(data.get("data") or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
            # Older database rows stored details directly; newer rows wrap them
            # with retry and duration metadata for a stable SSE event shape.
            wrapped = isinstance(payload, dict) and any(
                key in payload for key in ("details", "retry_count", "duration_ms")
            )
            events.append({
                "id": data["id"],
                "run_id": data["run_id"],
                "agent_name": data["agent_name"],
                "status": data["status"],
                "message": data["message"],
                "details": payload.get("details") if wrapped else payload or None,
                "error": payload.get("error") if wrapped else None,
                "retry_count": payload.get("retry_count", 0) if wrapped else 0,
                "timestamp": data["created_at"],
                "duration_ms": payload.get("duration_ms") if wrapped else None,
            })
        return events
    finally:
        conn.close()


def list_runs_for_student(student_id: str) -> List[Dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, status, created_at, updated_at FROM workflow_runs
               WHERE student_id = ? ORDER BY created_at DESC""",
            (student_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
