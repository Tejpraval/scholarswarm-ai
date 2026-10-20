"""Strict Pydantic schemas for LLM agent responses."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResearchFindingOutput(StrictAgentOutput):
    name: str = Field(min_length=2)
    provider: str = Field(min_length=2)
    country: str = Field(min_length=2)
    university: Optional[str] = None
    source_type: Literal["university", "government", "foundation", "corporate", "unknown"] = "unknown"
    degree_levels: list[str] = Field(default_factory=list)
    fields_of_study: list[str] = Field(default_factory=list)
    funding_type: Literal["full_funding", "partial_funding", "stipend_only", "tuition_only", "living_allowance", "unknown"] = "unknown"
    funding_description: str = ""
    funding_amount_usd: Optional[float] = None
    covers_tuition: Optional[bool] = None
    covers_living: Optional[bool] = None
    min_cgpa: Optional[float] = None
    required_language_tests: list[str] = Field(default_factory=list)
    citizenship_restrictions: list[str] = Field(default_factory=list)
    open_to_indian_nationals: Optional[bool] = None
    application_deadline: Optional[str] = None
    deadline_notes: str = ""
    official_url: Optional[str] = None
    source_url: str = Field(min_length=8)
    source_snippet: str = ""
    application_instructions: str = ""
    required_documents: list[str] = Field(default_factory=list)


class ResearchResponse(StrictAgentOutput):
    opportunities: list[ResearchFindingOutput]


RequirementCategory = Literal[
    "opportunity_exists",
    "degree_level",
    "international_eligibility",
    "academic_requirements",
    "language_requirements",
    "field_of_study",
    "funding",
    "deadline",
    "other",
]
CheckStatus = Literal["met", "not_met", "unknown", "partially_met", "not_applicable"]


class RequirementEvidenceOutput(StrictAgentOutput):
    category: RequirementCategory
    requirement: str = Field(min_length=2)
    student_value: Optional[str] = None
    required_value: Optional[str] = None
    status: CheckStatus
    evidence: Optional[str] = None
    source_url: Optional[str] = None


class EligibilityResponse(StrictAgentOutput):
    status: Literal["eligible", "potentially_eligible", "ineligible", "needs_verification"]
    confidence: float = Field(ge=0.0, le=1.0)
    requirement_checks: list[RequirementEvidenceOutput]
    missing_documents: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    disqualifying_factors: list[str] = Field(default_factory=list)
    notes: str = ""
