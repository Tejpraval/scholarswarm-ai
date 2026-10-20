"""Scholarship opportunity, eligibility, and match models."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime, date
from pydantic import BaseModel, Field
import uuid


class SourceType(str, Enum):
    UNIVERSITY = "university"
    GOVERNMENT = "government"
    FOUNDATION = "foundation"
    CORPORATE = "corporate"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceStage(str, Enum):
    NOT_CHECKED = "not_checked"
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class EligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    POTENTIALLY_ELIGIBLE = "potentially_eligible"
    INELIGIBLE = "ineligible"
    NEEDS_VERIFICATION = "needs_verification"


class FundingType(str, Enum):
    FULL = "full_funding"
    PARTIAL = "partial_funding"
    STIPEND = "stipend_only"
    TUITION = "tuition_only"
    LIVING = "living_allowance"
    UNKNOWN = "unknown"


class RequirementCheck(BaseModel):
    category: str = "other"
    requirement: str
    student_value: Optional[str] = None
    required_value: Optional[str] = None
    status: str  # met | not_met | unknown | partially_met
    evidence: Optional[str] = None
    source_url: Optional[str] = None


class EligibilityAssessment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scholarship_id: str
    student_id: str
    status: EligibilityStatus
    confidence: float = Field(ge=0.0, le=1.0, description="0.0 to 1.0")
    requirement_checks: List[RequirementCheck] = Field(default_factory=list)
    missing_documents: List[str] = Field(default_factory=list)
    missing_info: List[str] = Field(default_factory=list)
    disqualifying_factors: List[str] = Field(default_factory=list)
    notes: str = ""
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    source_verified: bool = False
    eligibility_assessed: bool = True


class ScholarshipOpportunity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    provider: str
    source_type: SourceType = SourceType.UNKNOWN
    country: str
    university: Optional[str] = None
    degree_levels: List[str] = Field(default_factory=list)
    fields_of_study: List[str] = Field(default_factory=list)
    # Funding details
    funding_type: FundingType = FundingType.UNKNOWN
    funding_amount_usd: Optional[float] = None
    funding_description: str = ""
    covers_tuition: Optional[bool] = None
    covers_living: Optional[bool] = None
    covers_travel: Optional[bool] = None
    # Requirements
    min_cgpa: Optional[float] = None
    required_language_tests: List[str] = Field(default_factory=list)
    citizenship_restrictions: List[str] = Field(default_factory=list)
    open_to_indian_nationals: Optional[bool] = None
    # Deadlines
    application_deadline: Optional[str] = None  # ISO date string or descriptive
    deadline_notes: str = ""
    # Source evidence
    official_url: Optional[str] = None
    application_url: Optional[str] = None
    application_url_status: str = "unknown"
    verification_date: Optional[date] = None
    official_source_urls: List[str] = Field(default_factory=list)
    source_url: str = ""
    source_snippet: str = ""
    retrieved_at: Optional[datetime] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    discovery_status: str = "discovered"
    official_source_status: EvidenceStage = EvidenceStage.NOT_CHECKED
    requirements_status: EvidenceStage = EvidenceStage.NOT_CHECKED
    deadline_status: EvidenceStage = EvidenceStage.UNKNOWN
    # Application info
    application_instructions: str = ""
    required_documents: List[str] = Field(default_factory=list)
    # Deduplication
    canonical_id: Optional[str] = None
    duplicate_of: Optional[str] = None


class MatchResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scholarship_id: str
    student_id: str
    rank: int
    match_score: float = Field(ge=0.0, le=100.0)
    eligibility_status: EligibilityStatus
    eligibility_confidence: float = Field(ge=0.0, le=1.0)
    # Score breakdown
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    # Explanation
    match_explanation: str = ""
    why_recommended: str = ""
    # Details
    scholarship: Optional[ScholarshipOpportunity] = None
    eligibility: Optional[EligibilityAssessment] = None
    missing_requirements: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    ranked_at: datetime = Field(default_factory=datetime.utcnow)
