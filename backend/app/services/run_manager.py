"""Manages active workflow runs and SSE event streaming."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import uuid
from typing import Dict, List, AsyncGenerator, Optional
from datetime import datetime

from app.models.workflow import WorkflowRun, RunStatus, AgentStatus, AgentRunState, AgentEvent
from app.models.student import StudentProfile
from app.agents.state import GraphState
from app.agents.orchestrator import run_workflow
from app.services import database as db
from app.utils.event_bus import register_run_queue, unregister_run_queue, publish_agent_event

logger = logging.getLogger(__name__)

# In-memory registry of active runs (supplemented by DB for persistence)
_active_runs: Dict[str, asyncio.Task] = {}
_run_states: Dict[str, GraphState] = {}
_run_event_queues: Dict[str, asyncio.Queue] = {}


async def start_run(profile: StudentProfile) -> str:
    """Start a new workflow run and return the run_id."""
    run_id = str(uuid.uuid4())

    # Save initial run state
    run_record = WorkflowRun(
        id=run_id,
        student_id=profile.id,
        status=RunStatus.QUEUED,
        started_at=datetime.utcnow(),
    )
    run_data = run_record.model_dump(mode="json")
    run_data["process_id"] = os.getpid()
    db.save_workflow_run(
        run_data,
        run_id=run_id,
        student_id=profile.id,
        status=RunStatus.QUEUED.value,
    )
    db.save_student_profile(profile)

    # Create event queue for SSE
    _run_event_queues[run_id] = asyncio.Queue(maxsize=500)
    register_run_queue(run_id, _run_event_queues[run_id])

    # Start the workflow as a background task
    task = asyncio.create_task(_execute_run(run_id, profile))
    _active_runs[run_id] = task

    return run_id


async def start_demo_run(profile: StudentProfile) -> str:
    """Start a curated fixture run without touching Gemini, Tavily, or LangGraph."""
    from app.services.demo_dataset import load_fixture, validate_demo_profile

    fixture = load_fixture()
    missing = validate_demo_profile(profile, fixture)
    if missing:
        raise ValueError(
            "The evidence-backed demo fixture is tied to its documented fictional profile. "
            "Restore the curated qualifications or choose Live Research. Missing: "
            + "; ".join(missing)
        )

    run_id = str(uuid.uuid4())
    run_record = WorkflowRun(
        id=run_id,
        student_id=profile.id,
        status=RunStatus.QUEUED,
        is_demo=True,
        started_at=datetime.utcnow(),
    )
    run_data = run_record.model_dump(mode="json")
    run_data.update({
        "process_id": os.getpid(),
        "mode": "curated_demo",
        "demo_dataset_id": fixture["dataset_id"],
        "verified_on": fixture["verified_on"],
    })
    db.save_workflow_run(run_data, run_id, profile.id, RunStatus.QUEUED.value)
    db.save_student_profile(profile)

    _run_event_queues[run_id] = asyncio.Queue(maxsize=500)
    register_run_queue(run_id, _run_event_queues[run_id])
    task = asyncio.create_task(_execute_demo_run(run_id, profile, fixture))
    _active_runs[run_id] = task
    return run_id


async def _execute_demo_run(run_id: str, profile: StudentProfile, fixture: Dict) -> None:
    """Load and persist a prepared evidence set; events describe fixture work, not AI agents."""
    from app.services.demo_dataset import build_demo_state

    events: list[AgentEvent] = []

    def emit(message: str, status: AgentStatus = AgentStatus.COMPLETED, details=None, error=None):
        event = AgentEvent(
            run_id=run_id,
            agent_name="curated_demo_fixture",
            status=status,
            message=message,
            details=details,
            error=error,
        )
        events.append(event)
        publish_agent_event(event)

    db.save_workflow_run(
        {"id": run_id, "status": RunStatus.RUNNING.value, "student_id": profile.id,
         "process_id": os.getpid(), "is_demo": True, "mode": "curated_demo",
         "demo_dataset_id": fixture["dataset_id"], "verified_on": fixture["verified_on"]},
        run_id=run_id, student_id=profile.id, status=RunStatus.RUNNING.value,
    )
    try:
        emit(
            "Loading the curated demonstration dataset (no AI provider calls).",
            AgentStatus.RUNNING,
            {"mode": "curated_demo", "dataset_id": fixture["dataset_id"]},
        )
        await asyncio.sleep(0.2)
        state, fixture = await build_demo_state(run_id, profile)
        emit(
            f"Loaded {len(state.discovered_opportunities)} prepared opportunities verified on {fixture['verified_on']}.",
            details={"verified_on": fixture["verified_on"], "opportunities": len(state.discovered_opportunities)},
        )
        await asyncio.sleep(0.2)
        emit(
            "Applied the fixture's documented eligibility assessments; unresolved criteria remain unconfirmed.",
            details={
                "confirmed": sum(a.status.value == "eligible" for a in state.eligibility_assessments),
                "unresolved": sum(a.status.value == "needs_verification" for a in state.eligibility_assessments),
            },
        )
        await asyncio.sleep(0.2)
        emit(
            f"Prepared {len(state.top_matches)} evidence-backed recommendation(s) and "
            f"{'a' if state.sop_draft else 'no'} profile-fact SOP draft.",
            details={"recommendations": len(state.top_matches), "sop_generated": state.sop_draft is not None},
        )

        state.events = events
        _run_states[run_id] = state
        db.save_scholarships(run_id, state.discovered_opportunities)
        db.save_eligibility_assessments(run_id, state.eligibility_assessments)
        db.save_match_results(run_id, state.match_results)
        if state.sop_draft:
            db.save_sop_draft(state.sop_draft)
        db.save_events(run_id, events)

        run_data = {
            "id": run_id,
            "status": RunStatus.COMPLETED.value,
            "student_id": profile.id,
            "process_id": os.getpid(),
            "is_demo": True,
            "mode": "curated_demo",
            "demo_dataset_id": fixture["dataset_id"],
            "verified_on": fixture["verified_on"],
            "opportunities_found": len(state.discovered_opportunities),
            "opportunities_verified": sum(o.official_source_status.value == "verified" for o in state.discovered_opportunities),
            "requirements_verified": sum(o.requirements_status.value == "verified" for o in state.discovered_opportunities),
            "deadlines_verified": sum(o.deadline_status.value == "verified" for o in state.discovered_opportunities),
            "eligible_confirmed": sum(a.status.value == "eligible" for a in state.eligibility_assessments),
            "top_matches": len(state.top_matches),
            "sop_generated": state.sop_draft is not None,
            "completed_at": datetime.utcnow().isoformat(),
        }
        db.save_workflow_run(run_data, run_id, profile.id, RunStatus.COMPLETED.value)
        queue = _run_event_queues.get(run_id)
        if queue:
            await queue.put({"type": "complete", "data": run_data})
    except Exception as exc:
        logger.exception("Curated demo run %s failed", run_id)
        run_data = {
            "id": run_id,
            "status": RunStatus.FAILED.value,
            "student_id": profile.id,
            "is_demo": True,
            "mode": "curated_demo",
            "error": str(exc),
            "workflow_error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        }
        db.save_events(run_id, events)
        db.save_workflow_run(run_data, run_id, profile.id, RunStatus.FAILED.value)
        queue = _run_event_queues.get(run_id)
        if queue:
            await queue.put({"type": "error", "data": {"error": str(exc)}})
    finally:
        unregister_run_queue(run_id)


async def _execute_run(run_id: str, profile: StudentProfile) -> None:
    """Execute the workflow and persist results."""
    logger.info(f"Executing workflow run {run_id} for student {profile.id}")

    # Update status to running
    db.save_workflow_run(
        {"id": run_id, "status": RunStatus.RUNNING.value, "student_id": profile.id,
         "process_id": os.getpid()},
        run_id=run_id,
        student_id=profile.id,
        status=RunStatus.RUNNING.value,
    )

    try:
        final_state = await run_workflow(run_id, profile.id, profile)
        _run_states[run_id] = final_state

        # Persist results
        if final_state.discovered_opportunities:
            db.save_scholarships(run_id, final_state.discovered_opportunities)

        if final_state.eligibility_assessments:
            db.save_eligibility_assessments(run_id, final_state.eligibility_assessments)

        if final_state.match_results:
            db.save_match_results(run_id, final_state.match_results)

        if final_state.sop_draft:
            db.save_sop_draft(final_state.sop_draft)

        if final_state.events:
            db.save_events(run_id, final_state.events)

        verified_count = sum(
            1 for opp in final_state.discovered_opportunities
            if opp.official_source_status.value == "verified"
        )
        requirements_verified_count = sum(
            1 for opp in final_state.discovered_opportunities
            if opp.requirements_status.value == "verified"
        )
        deadline_verified_count = sum(
            1 for opp in final_state.discovered_opportunities
            if opp.deadline_status.value == "verified"
        )
        eligible_count = sum(
            1 for assessment in final_state.eligibility_assessments
            if assessment.status.value == "eligible"
        )
        has_unverified = verified_count < len(final_state.discovered_opportunities)
        partial_reasons = []
        if final_state.research_error:
            partial_reasons.append(final_state.research_error)
        if final_state.verification_errors:
            partial_reasons.append(f"{len(final_state.verification_errors)} eligibility verification error(s).")
        if has_unverified:
            partial_reasons.append(
                f"{len(final_state.discovered_opportunities) - verified_count} opportunity/opportunities lack a fetched official source."
            )
        if requirements_verified_count < len(final_state.discovered_opportunities):
            partial_reasons.append(
                f"{len(final_state.discovered_opportunities) - requirements_verified_count} opportunity/opportunities have incomplete critical requirement evidence."
            )
        if not final_state.discovered_opportunities:
            partial_reasons.append("No scholarship opportunities were discovered.")
        if partial_reasons and not final_state.workflow_error:
            final_state.workflow_error = " ".join(partial_reasons)
        status = RunStatus.PARTIAL if final_state.workflow_error else RunStatus.COMPLETED
        run_data = {
            "id": run_id,
            "status": status.value,
            "student_id": profile.id,
            "process_id": os.getpid(),
            "opportunities_found": len(final_state.discovered_opportunities),
            "opportunities_verified": verified_count,
            "official_sources_located": verified_count,
            "requirements_verified": requirements_verified_count,
            "deadlines_verified": deadline_verified_count,
            "eligible_confirmed": eligible_count,
            "top_matches": len(final_state.top_matches),
            "sop_generated": final_state.sop_draft is not None,
            "workflow_error": final_state.workflow_error,
            "research_error": final_state.research_error,
            "verification_errors": len(final_state.verification_errors),
            "verification_error_details": final_state.verification_errors,
            "completed_at": datetime.utcnow().isoformat(),
        }
        db.save_workflow_run(run_data, run_id=run_id, student_id=profile.id, status=status.value)

        # Signal SSE completion
        queue = _run_event_queues.get(run_id)
        if queue:
            await queue.put({"type": "complete", "data": run_data})
        unregister_run_queue(run_id)

        logger.info(f"Run {run_id} completed with status {status.value}")

    except Exception as e:
        logger.error(f"Run {run_id} failed: {e}", exc_info=True)
        db.save_workflow_run(
            {"id": run_id, "status": RunStatus.FAILED.value, "error": str(e),
             "student_id": profile.id, "process_id": os.getpid()},
            run_id=run_id,
            student_id=profile.id,
            status=RunStatus.FAILED.value,
        )
        queue = _run_event_queues.get(run_id)
        if queue:
            await queue.put({"type": "error", "data": {"error": str(e)}})
        unregister_run_queue(run_id)


def get_run_status(run_id: str) -> Optional[Dict]:
    """Get run status from DB."""
    return db.get_workflow_run(run_id)


def get_run_events(run_id: str) -> List[Dict]:
    """Get all events for a run from DB (or in-memory if still running)."""
    state = _run_states.get(run_id)
    if state:
        return [
            {
                "id": ev.id,
                "run_id": ev.run_id,
                "agent_name": ev.agent_name,
                "status": ev.status.value,
                "message": ev.message,
                "details": ev.details,
                "error": ev.error,
                "timestamp": ev.timestamp.isoformat(),
                "duration_ms": ev.duration_ms,
            }
            for ev in state.events
        ]
    return db.get_events_for_run(run_id)


def get_run_results(run_id: str) -> Optional[Dict]:
    """Get full results for a completed run."""
    state = _run_states.get(run_id)
    if state:
        run_record = db.get_workflow_run(run_id) or {}
        return {
            "run_id": run_id,
            "discovered_count": len(state.discovered_opportunities),
            "scholarships": [json.loads(s.model_dump_json()) for s in state.discovered_opportunities],
            "top_matches": [json.loads(m.model_dump_json()) for m in state.top_matches],
            "all_matches": [json.loads(m.model_dump_json()) for m in state.match_results],
            "sop_draft": json.loads(state.sop_draft.model_dump_json()) if state.sop_draft else None,
            "workflow_error": state.workflow_error,
            "research_error": state.research_error,
            "run_mode": run_record.get("mode", "live"),
            "demo_dataset_id": run_record.get("demo_dataset_id"),
            "verified_on": run_record.get("verified_on"),
        }

    # Fallback to DB
    scholarships = db.get_scholarships_for_run(run_id)
    matches = db.get_match_results_for_run(run_id)
    sop = db.get_sop_draft(run_id)
    if not scholarships and not matches:
        run = db.get_workflow_run(run_id)
        if not run or run.get("status") in (RunStatus.QUEUED.value, RunStatus.RUNNING.value):
            return None
        # A completed run may legitimately have no matches, while a partial or
        # failed run may have no persisted result rows. Return a stable shape so
        # clients can show the run outcome instead of crashing on missing lists.
        return {
            "run_id": run_id,
            "discovered_count": 0,
            "scholarships": [],
            "top_matches": [],
            "all_matches": [],
            "sop_draft": None,
            "workflow_error": run.get("workflow_error") or run.get("error"),
            "research_error": None,
            "run_mode": run.get("mode", "live"),
            "demo_dataset_id": run.get("demo_dataset_id"),
            "verified_on": run.get("verified_on"),
        }

    run = db.get_workflow_run(run_id) or {}
    top_matches = []
    seen = set()
    profile_data = db.get_student_profile(run.get("student_id", ""))
    if profile_data:
        try:
            from app.agents.matcher import _is_recommendable, _recommendation_key
            from app.models.scholarship import MatchResult
            profile = StudentProfile.model_validate(profile_data)
            for match in matches:
                parsed_match = MatchResult.model_validate(match)
                if not _is_recommendable(parsed_match, profile):
                    continue
                key = _recommendation_key(parsed_match)
                if key in seen:
                    continue
                seen.add(key)
                top_matches.append(match)
                if len(top_matches) == 5:
                    break
        except Exception:
            logger.exception("Could not reconstruct confirmed matches from persisted run %s", run_id)
            top_matches = []
    return {
        "run_id": run_id,
        "discovered_count": len(scholarships),
        "scholarships": scholarships,
        "top_matches": top_matches,
        "all_matches": matches,
        "sop_draft": sop,
        "workflow_error": run.get("workflow_error") or run.get("error"),
        "research_error": run.get("research_error"),
        "official_sources_located": run.get("official_sources_located"),
        "requirements_verified": run.get("requirements_verified"),
        "deadlines_verified": run.get("deadlines_verified"),
        "eligible_confirmed": run.get("eligible_confirmed"),
        "run_mode": run.get("mode", "live"),
        "demo_dataset_id": run.get("demo_dataset_id"),
        "verified_on": run.get("verified_on"),
    }


async def stream_run_events(run_id: str) -> AsyncGenerator[str, None]:
    """
    SSE generator that yields events for a run.
    Streams both historical events and new events as they arrive.
    """
    import json

    # First, emit all existing events
    existing_events = get_run_events(run_id)
    for ev in existing_events:
        yield f"data: {json.dumps({'type': 'event', 'data': ev})}\n\n"

    # Check if run is still in progress
    if run_id not in _active_runs or _active_runs[run_id].done():
        run = get_run_status(run_id)
        if run:
            status = run.get("status", "unknown")
            if status in (RunStatus.COMPLETED.value, RunStatus.PARTIAL.value):
                yield f"data: {json.dumps({'type': 'complete', 'data': run})}\n\n"
            elif status == RunStatus.FAILED.value:
                yield f"data: {json.dumps({'type': 'error', 'data': {'error': run.get('error') or 'Workflow failed'}})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'status', 'data': {'status': status}})}\n\n"
        return

    # Stream new events from the queue
    queue = _run_event_queues.get(run_id)
    if not queue:
        return

    # Wait for events with timeout
    timeout_count = 0
    max_timeouts = 120  # 120 * 1s = 2 minutes max wait per message
    while True:
        try:
            msg = await asyncio.wait_for(queue.get(), timeout=1.0)
            yield f"data: {json.dumps(msg)}\n\n"

            if msg.get("type") in ("complete", "error"):
                break
            timeout_count = 0

        except asyncio.TimeoutError:
            timeout_count += 1
            # Send heartbeat
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            if timeout_count >= max_timeouts:
                break
            # Check if task completed
            task = _active_runs.get(run_id)
            if task and task.done() and queue.empty():
                yield f"data: {json.dumps({'type': 'complete', 'data': {'status': 'completed'}})}\n\n"
                break
