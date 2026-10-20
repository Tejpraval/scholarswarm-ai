"""Application draft (SOP) model."""
from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class ApplicationDraft(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    student_id: str
    scholarship_id: str
    scholarship_name: str
    university: Optional[str] = None
    # Content
    draft_text: str
    placeholders: List[str] = Field(
        default_factory=list,
        description="List of [PLACEHOLDER] tokens in the draft that need real info"
    )
    word_count: int = 0
    # Metadata
    is_draft: bool = True  # Always true — we never submit
    facts_used: List[str] = Field(
        default_factory=list,
        description="Facts from student profile used in this SOP"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about missing info or uncertain claims"
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
