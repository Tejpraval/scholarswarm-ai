"""Student profile and document models."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, field_validator
import uuid


class DegreeLevel(str, Enum):
    BACHELORS = "bachelors"
    MASTERS = "masters"
    PHD = "phd"
    POSTDOC = "postdoc"


class FundingPreference(str, Enum):
    FULL = "full_funding"
    PARTIAL = "partial_funding"
    ANY = "any"


class DocumentType(str, Enum):
    RESUME = "resume"
    MARKSHEET = "marksheet"
    OTHER = "other"


class DocumentUpload(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_type: DocumentType
    filename: str
    file_path: str  # server-side path only, never exposed publicly
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    extracted_text: Optional[str] = None
    extraction_status: str = "pending"  # pending | done | failed


class AcademicProfile(BaseModel):
    degree_level: Optional[DegreeLevel] = None
    degree_name: Optional[str] = None
    institution: Optional[str] = None
    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    cgpa_scale: Optional[float] = Field(None, ge=4.0, le=10.0, description="Max CGPA scale e.g. 10.0")
    graduation_year: Optional[int] = None
    graduation_month: Optional[int] = None
    major: Optional[str] = None
    country_of_study: Optional[str] = None
    language_scores: Optional[Dict[str, Any]] = Field(
        default=None,
        description="e.g. {'IELTS': 7.0, 'TOEFL': 100, 'GRE': 320}"
    )

    @field_validator("graduation_year")
    @classmethod
    def year_reasonable(cls, v):
        if v and (v < 1990 or v > 2035):
            raise ValueError("Graduation year seems out of range")
        return v


class StudentProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: Optional[str] = None
    nationality: Optional[str] = None
    country_of_residence: Optional[str] = None
    academic: AcademicProfile = Field(default_factory=AcademicProfile)
    skills: List[str] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    work_experience: List[Dict[str, Any]] = Field(default_factory=list)
    publications: List[str] = Field(default_factory=list)
    research_interests: List[str] = Field(default_factory=list)
    destination_preferences: List[str] = Field(
        default_factory=list,
        description="Preferred countries to study in"
    )
    target_degree: Optional[DegreeLevel] = None
    target_field: Optional[str] = None
    funding_preference: FundingPreference = FundingPreference.ANY
    budget_usd_per_year: Optional[float] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    personal_statement_notes: Optional[str] = None
    documents: List[DocumentUpload] = Field(default_factory=list)
    # Enrichment metadata
    profile_completeness: float = 0.0
    missing_fields: List[str] = Field(default_factory=list)
    github_enrichment: Optional[Dict[str, Any]] = None
    extracted_from_documents: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Default demo profile for Rahul
DEMO_PROFILE = StudentProfile(
    id="demo-rahul-001",
    name="Rahul Sharma",
    email="rahul.sharma@example.com",
    nationality="Indian",
    country_of_residence="India",
    academic=AcademicProfile(
        degree_level=DegreeLevel.BACHELORS,
        degree_name="B.Tech Computer Science",
        institution="Lovely Professional University, Jalandhar",
        cgpa=8.2,
        cgpa_scale=10.0,
        graduation_year=2025,
        major="Computer Science and Engineering",
        country_of_study="India",
        language_scores={}  # No IELTS/TOEFL taken yet
    ),
    skills=[
        "Python", "Machine Learning", "TensorFlow", "PyTorch",
        "Natural Language Processing", "Computer Vision",
        "SQL", "Git", "Docker", "REST APIs", "FastAPI", "React"
    ],
    projects=[
        {
            "name": "Crop Disease Detection using CNN",
            "description": "Built a convolutional neural network to classify crop diseases from leaf images.",
            "technologies": ["Python", "TensorFlow", "OpenCV"],
            "source": "stated by student"
        },
        {
            "name": "Chatbot for College FAQ",
            "description": "Developed an NLP chatbot using transformers to answer college-related queries.",
            "technologies": ["Python", "HuggingFace Transformers", "FastAPI"],
            "source": "stated by student"
        }
    ],
    achievements=[
        "Participated in Smart India Hackathon 2024",
        "Presented paper at college technical symposium"
    ],
    research_interests=["Artificial Intelligence", "Machine Learning", "Computer Vision", "NLP"],
    destination_preferences=["Canada", "Germany", "Singapore"],
    target_degree=DegreeLevel.MASTERS,
    target_field="Artificial Intelligence / Machine Learning",
    funding_preference=FundingPreference.FULL,
    budget_usd_per_year=5000,  # Very limited — needs full funding
    github_url="https://github.com/rahul-sharma-example",  # placeholder
    personal_statement_notes=(
        "First-generation college student from Jalandhar. Family has limited financial resources. "
        "Strong interest in applied AI for social good. Seeking fully funded masters programs."
    )
)
