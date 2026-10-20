"""Shared typed state for the LangGraph workflow."""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Annotated
from datetime import datetime
from pydantic import BaseModel, Field
import operator

from app.models.student import StudentProfile
from app.models.scholarship import ScholarshipOpportunity, EligibilityAssessment, MatchResult
from app.models.workflow import AgentEvent, AgentStatus
from app.models.application import ApplicationDraft


def _merge_lists(a: list, b: list) -> list:
    """Merge two lists, used as reducer for LangGraph state."""
    return a + b


class GraphState(BaseModel):
    """Shared state passed between all agents in the workflow."""
    # Run metadata
    run_id: str
    student_id: str

    # Student profile (mutable as agents enrich it)
    student_profile: Optional[StudentProfile] = None
    profile_validated: bool = False
    profile_issues: List[str] = Field(default_factory=list)

    # Agent 1 output
    enriched_profile: Optional[StudentProfile] = None
    github_data: Optional[Dict[str, Any]] = None

    # Agent 2 output
    discovered_opportunities: List[ScholarshipOpportunity] = Field(default_factory=list)
    research_queries_used: List[str] = Field(default_factory=list)
    research_error: Optional[str] = None
    research_retry_count: int = 0

    # Agent 3 output
    eligibility_assessments: List[EligibilityAssessment] = Field(default_factory=list)
    verification_errors: List[str] = Field(default_factory=list)

    # Agent 4 output
    match_results: List[MatchResult] = Field(default_factory=list)
    top_matches: List[MatchResult] = Field(default_factory=list)
    sop_draft: Optional[ApplicationDraft] = None

    # Events log (append-only across all agents)
    events: List[AgentEvent] = Field(default_factory=list)

    # Control flow
    should_retry_research: bool = False
    workflow_error: Optional[str] = None
    completed_agents: List[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
