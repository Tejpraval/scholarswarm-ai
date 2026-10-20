"""Workflow run and agent event models."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AgentEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    agent_name: str
    status: AgentStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None


class AgentRunState(BaseModel):
    name: str
    status: AgentStatus = AgentStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error: Optional[str] = None
    result_summary: Optional[str] = None


class WorkflowRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    student_id: str
    status: RunStatus = RunStatus.QUEUED
    agents: Dict[str, AgentRunState] = Field(default_factory=dict)
    events: List[AgentEvent] = Field(default_factory=list)
    # Counts
    opportunities_found: int = 0
    opportunities_verified: int = 0
    top_matches: int = 0
    # Results (IDs only — full data in DB)
    scholarship_ids: List[str] = Field(default_factory=list)
    match_ids: List[str] = Field(default_factory=list)
    sop_draft_id: Optional[str] = None
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    # Flags
    is_demo: bool = False
    retry_of: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
