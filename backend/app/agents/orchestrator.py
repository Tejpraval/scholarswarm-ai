"""LangGraph-based workflow orchestrator for ScholarSwarm AI."""
from __future__ import annotations
import logging
import asyncio
from typing import Any, Dict
from datetime import datetime

# langchain-core 0.2 reads legacy `langchain.debug` and `langchain.verbose`
# attributes. LangChain 1.x no longer exposes them, so provide their default
# values before importing LangGraph (which may read these settings at import
# or invocation time).
try:
    import langchain

    if not hasattr(langchain, "debug"):
        langchain.debug = False
    if not hasattr(langchain, "verbose"):
        langchain.verbose = False
except ImportError:
    pass

from langgraph.graph import StateGraph, END

from app.agents.state import GraphState
from app.agents.profiler import run_profiler
from app.agents.researcher import run_researcher
from app.agents.verifier import run_verifier
from app.agents.matcher import run_matcher
from app.models.workflow import AgentEvent, AgentStatus, RunStatus, WorkflowRun
from app.utils.event_bus import publish_agent_event

logger = logging.getLogger(__name__)


# ── Node wrappers ──────────────────────────────────────────────────────────────

async def profiler_node(state: GraphState) -> GraphState:
    return await run_profiler(state)


async def researcher_node(state: GraphState) -> GraphState:
    return await run_researcher(state)


async def verifier_node(state: GraphState) -> GraphState:
    return await run_verifier(state)


async def matcher_node(state: GraphState) -> GraphState:
    return await run_matcher(state)


async def validate_output_node(state: GraphState) -> GraphState:
    """Final validation step — checks that results are coherent."""
    ev = AgentEvent(
        run_id=state.run_id,
        agent_name="output_validator",
        status=AgentStatus.RUNNING,
        message="Validating final outputs for consistency and evidence completeness",
    )
    state.events.append(ev)
    publish_agent_event(ev)

    issues = []
    # Check every top match has an official URL or at least a source URL
    for match in state.top_matches:
        opp = match.scholarship
        if opp and not opp.official_url and not opp.source_url:
            issues.append(f"{opp.name}: no source URL recorded")

    # Check SOP doesn't have too many unresolved placeholders
    if state.sop_draft and len(state.sop_draft.placeholders) > 8:
        issues.append("SOP has many placeholders — profile may be incomplete")

    completion_ev = AgentEvent(
        run_id=state.run_id,
        agent_name="output_validator",
        status=AgentStatus.COMPLETED,
        message=(
            f"Output validation complete. "
            f"{len(state.top_matches)} recommendations, "
            f"{len(state.discovered_opportunities)} total opportunities. "
            + (f"Warnings: {'; '.join(issues)}" if issues else "No issues found.")
        ),
        details={"issues": issues, "warnings_count": len(issues)},
    )
    state.events.append(completion_ev)
    publish_agent_event(completion_ev)
    return state


# ── Conditional edges ──────────────────────────────────────────────────────────

def route_after_profiler(state: GraphState) -> str:
    """Route: if profile is missing critical info, still continue."""
    if state.workflow_error:
        return "end"
    return "researcher"


def route_after_researcher(state: GraphState) -> str:
    """Route: if no opportunities found, skip to matcher with empty results."""
    if not state.discovered_opportunities:
        return "validate_output"  # Skip verifier and matcher
    return "verifier"


def route_after_verifier(state: GraphState) -> str:
    """Always proceed to matcher regardless of verification errors."""
    return "matcher"


def route_after_matcher(state: GraphState) -> str:
    return "validate_output"


# ── Graph construction ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("profiler", profiler_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("matcher", matcher_node)
    graph.add_node("validate_output", validate_output_node)

    # Entry point
    graph.set_entry_point("profiler")

    # Conditional edges
    graph.add_conditional_edges(
        "profiler",
        route_after_profiler,
        {"researcher": "researcher", "end": END},
    )
    graph.add_conditional_edges(
        "researcher",
        route_after_researcher,
        {"verifier": "verifier", "validate_output": "validate_output"},
    )
    graph.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {"matcher": "matcher"},
    )
    graph.add_conditional_edges(
        "matcher",
        route_after_matcher,
        {"validate_output": "validate_output"},
    )
    graph.add_edge("validate_output", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def run_workflow(
    run_id: str,
    student_id: str,
    profile,
    run_store: Any = None,
) -> GraphState:
    """Execute the full workflow and return final state."""
    initial_state = GraphState(
        run_id=run_id,
        student_id=student_id,
        student_profile=profile,
    )

    # Emit start event
    start_event = AgentEvent(
        run_id=run_id,
        agent_name="orchestrator",
        status=AgentStatus.RUNNING,
        message=f"Workflow started for student: {profile.name}",
        details={"student_id": student_id, "student_name": profile.name},
    )
    initial_state.events.append(start_event)
    publish_agent_event(start_event)

    graph = get_graph()
    try:
        final_state = await graph.ainvoke(initial_state)
        # ainvoke returns a dict for StateGraph — reconstruct
        if isinstance(final_state, dict):
            final_state = GraphState(**final_state)

        completion_event = AgentEvent(
            run_id=run_id,
            agent_name="orchestrator",
            status=AgentStatus.COMPLETED,
            message=(
                f"Workflow completed. "
                f"Discovered: {len(final_state.discovered_opportunities)}, "
                f"Top matches: {len(final_state.top_matches)}, "
                f"SOP: {'yes' if final_state.sop_draft else 'no'}"
            ),
        )
        final_state.events.append(completion_event)
        publish_agent_event(completion_event)
        return final_state

    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        initial_state.workflow_error = str(e)
        failure_event = AgentEvent(
            run_id=run_id,
            agent_name="orchestrator",
            status=AgentStatus.FAILED,
            message=f"Workflow encountered a fatal error: {str(e)[:200]}",
            error=str(e),
        )
        initial_state.events.append(failure_event)
        publish_agent_event(failure_event)
        return initial_state
