"""FastAPI route definitions for ScholarSwarm AI."""
from __future__ import annotations
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.models.student import StudentProfile, AcademicProfile, DegreeLevel, FundingPreference, DocumentUpload, DocumentType, DEMO_PROFILE
from app.models.workflow import RunStatus
from app.services import database as db
from app.services import run_manager
from app.utils.pdf_extractor import extract_text_safe

logger = logging.getLogger(__name__)

router = APIRouter()

# Upload directory — never exposed publicly
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_CONTENT_TYPES = {"application/pdf"}


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ScholarSwarm AI",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Student Profile ────────────────────────────────────────────────────────────

class ProfileCreateRequest(BaseModel):
    name: str
    email: Optional[str] = None
    nationality: Optional[str] = None
    country_of_residence: Optional[str] = None
    degree_level: Optional[str] = None
    degree_name: Optional[str] = None
    institution: Optional[str] = None
    cgpa: Optional[float] = None
    cgpa_scale: Optional[float] = 10.0
    graduation_year: Optional[int] = None
    major: Optional[str] = None
    skills: List[str] = []
    research_interests: List[str] = []
    destination_preferences: List[str] = []
    target_degree: Optional[str] = None
    target_field: Optional[str] = None
    funding_preference: str = "any"
    budget_usd_per_year: Optional[float] = None
    github_url: Optional[str] = None
    personal_statement_notes: Optional[str] = None


@router.post("/profiles", status_code=201)
async def create_profile(req: ProfileCreateRequest):
    """Create a new student profile."""
    try:
        profile = StudentProfile(
            name=req.name,
            email=req.email,
            nationality=req.nationality,
            country_of_residence=req.country_of_residence,
            academic=AcademicProfile(
                degree_level=DegreeLevel(req.degree_level) if req.degree_level else None,
                degree_name=req.degree_name,
                institution=req.institution,
                cgpa=req.cgpa,
                cgpa_scale=req.cgpa_scale,
                graduation_year=req.graduation_year,
                major=req.major,
            ),
            skills=req.skills,
            research_interests=req.research_interests,
            destination_preferences=req.destination_preferences,
            target_degree=DegreeLevel(req.target_degree) if req.target_degree else None,
            target_field=req.target_field,
            funding_preference=FundingPreference(req.funding_preference),
            budget_usd_per_year=req.budget_usd_per_year,
            github_url=req.github_url,
            personal_statement_notes=req.personal_statement_notes,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.save_student_profile(profile)
    return {"profile_id": profile.id, "profile": profile.model_dump(mode="json")}


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str):
    """Get a student profile."""
    if profile_id == "demo":
        return DEMO_PROFILE.model_dump(mode="json")
    data = db.get_student_profile(profile_id)
    if not data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return data


@router.put("/profiles/{profile_id}")
async def update_profile(profile_id: str, req: ProfileCreateRequest):
    """Update a student profile."""
    existing = db.get_student_profile(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile = StudentProfile(**existing)
    updates = {
        "name": req.name,
        "email": req.email,
        "nationality": req.nationality,
        "country_of_residence": req.country_of_residence,
        "academic": AcademicProfile(
            degree_level=DegreeLevel(req.degree_level) if req.degree_level else profile.academic.degree_level,
            degree_name=req.degree_name or profile.academic.degree_name,
            institution=req.institution or profile.academic.institution,
            cgpa=req.cgpa if req.cgpa is not None else profile.academic.cgpa,
            cgpa_scale=req.cgpa_scale or profile.academic.cgpa_scale,
            graduation_year=req.graduation_year or profile.academic.graduation_year,
            major=req.major or profile.academic.major,
            language_scores=profile.academic.language_scores,
        ),
        "skills": req.skills or profile.skills,
        "research_interests": req.research_interests or profile.research_interests,
        "destination_preferences": req.destination_preferences or profile.destination_preferences,
        "target_degree": DegreeLevel(req.target_degree) if req.target_degree else profile.target_degree,
        "target_field": req.target_field or profile.target_field,
        "funding_preference": FundingPreference(req.funding_preference),
        "budget_usd_per_year": req.budget_usd_per_year if req.budget_usd_per_year is not None else profile.budget_usd_per_year,
        "github_url": req.github_url or profile.github_url,
        "personal_statement_notes": req.personal_statement_notes or profile.personal_statement_notes,
        "updated_at": datetime.utcnow(),
    }
    updated = profile.model_copy(update=updates)
    db.save_student_profile(updated)
    return {"profile_id": profile_id, "profile": updated.model_dump(mode="json")}


# ── Document Upload ────────────────────────────────────────────────────────────

@router.post("/profiles/{profile_id}/documents")
async def upload_document(
    profile_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a PDF document (resume or marksheet) for a profile."""
    # Validate profile
    profile_data = db.get_student_profile(profile_id)
    if profile_data is None and profile_id != "demo":
        raise HTTPException(status_code=404, detail="Profile not found")

    # Validate doc type
    if doc_type not in [t.value for t in DocumentType]:
        raise HTTPException(status_code=400, detail=f"Invalid doc_type. Use: {[t.value for t in DocumentType]}")

    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Read and size-check
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if b"%PDF-" not in content[:1024]:
        raise HTTPException(status_code=400, detail="Uploaded file does not contain a valid PDF header")

    # Save to disk
    doc_id = str(uuid.uuid4())
    safe_filename = f"{doc_id}_{doc_type}.pdf"
    file_path = UPLOAD_DIR / safe_filename
    file_path.write_bytes(content)

    # Extract text
    extracted_text, error = extract_text_safe(str(file_path))
    extraction_status = "done" if extracted_text else "failed"

    doc = DocumentUpload(
        id=doc_id,
        doc_type=DocumentType(doc_type),
        filename=file.filename or safe_filename,
        file_path=str(file_path),  # Server-side only
        extracted_text=extracted_text,
        extraction_status=extraction_status,
    )

    # Update profile with document
    if profile_data:
        profile = StudentProfile(**profile_data)
        profile.documents.append(doc)
        profile.extracted_from_documents = True
        db.save_student_profile(profile)

    return {
        "document_id": doc_id,
        "doc_type": doc_type,
        "filename": file.filename,
        "extraction_status": extraction_status,
        "chars_extracted": len(extracted_text) if extracted_text else 0,
        "extraction_error": error,
        # NEVER return file_path or extracted_text in response
    }


# ── Workflow Runs ──────────────────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    profile_id: str


@router.post("/runs", status_code=202)
async def start_run(req: StartRunRequest):
    """Start a new research workflow run."""
    if req.profile_id == "demo":
        profile = DEMO_PROFILE
        # Save demo profile to DB for tracking
        db.save_student_profile(profile)
    else:
        profile_data = db.get_student_profile(req.profile_id)
        if not profile_data:
            raise HTTPException(status_code=404, detail="Profile not found")
        profile = StudentProfile(**profile_data)

    run_id = await run_manager.start_run(profile)
    return {
        "run_id": run_id,
        "student_id": profile.id,
        "status": "queued",
        "message": "Workflow started. Use /runs/{run_id}/events for live progress.",
    }


@router.post("/demo/runs", status_code=202)
async def start_demo_run(req: StartRunRequest):
    """Run the separately curated evidence fixture without calling AI providers."""
    profile_data = db.get_student_profile(req.profile_id)
    if not profile_data:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile = StudentProfile.model_validate(profile_data)
    try:
        run_id = await run_manager.start_demo_run(profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "run_id": run_id,
        "student_id": profile.id,
        "status": "queued",
        "mode": "curated_demo",
        "message": "Curated demonstration data is loading. Gemini and Tavily are not called.",
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Get run status and summary."""
    data = run_manager.get_run_status(run_id)
    if not data:
        raise HTTPException(status_code=404, detail="Run not found")
    return data


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str):
    """SSE endpoint — streams agent events in real time."""
    # Verify run exists
    if not run_manager.get_run_status(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    return StreamingResponse(
        run_manager.stream_run_events(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}/results")
async def get_results(run_id: str):
    """Get full scholarship results for a completed run."""
    data = run_manager.get_run_results(run_id)
    if not data:
        status = run_manager.get_run_status(run_id)
        if not status:
            raise HTTPException(status_code=404, detail="Run not found")
        if status.get("status") in ("queued", "running"):
            return JSONResponse(
                status_code=202,
                content={"message": "Run is still in progress", "status": status.get("status")}
            )
        raise HTTPException(status_code=404, detail="No results found for this run")
    return data


@router.get("/runs/{run_id}/scholarships/{scholarship_id}")
async def get_scholarship_detail(run_id: str, scholarship_id: str):
    """Get detailed info for a specific scholarship including eligibility."""
    results = run_manager.get_run_results(run_id)
    if not results:
        raise HTTPException(status_code=404, detail="Run not found or incomplete")

    scholarships = results.get("scholarships", [])
    scholarship = next((s for s in scholarships if s.get("id") == scholarship_id), None)
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found in this run")

    eligibility = db.get_eligibility_for_scholarship(run_id, scholarship_id)
    return {
        "scholarship": scholarship,
        "eligibility": eligibility,
    }


@router.post("/runs/{run_id}/sop")
async def generate_sop(run_id: str):
    """Generate (or retrieve) SOP draft for the best match in a run."""
    results = run_manager.get_run_results(run_id)
    if not results:
        raise HTTPException(status_code=404, detail="Run not found or no results")

    # Check if SOP already generated
    sop = results.get("sop_draft")
    if sop:
        return sop

    raise HTTPException(
        status_code=404,
        detail="No SOP draft available for this run. The matching agent may not have generated one."
    )


@router.post("/runs/{run_id}/retry")
async def retry_run(run_id: str):
    """Retry a failed run."""
    existing = run_manager.get_run_status(run_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Run not found")

    status = existing.get("status")
    if status not in ("failed", "partial"):
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry failed/partial runs. Current status: {status}"
        )

    student_id = existing.get("student_id")
    if not student_id:
        raise HTTPException(status_code=400, detail="Cannot determine student for retry")

    profile_data = db.get_student_profile(student_id)
    if not profile_data:
        raise HTTPException(status_code=404, detail="Student profile not found for retry")

    profile = StudentProfile(**profile_data)
    new_run_id = await run_manager.start_run(profile)

    return {
        "new_run_id": new_run_id,
        "original_run_id": run_id,
        "status": "queued",
        "message": "Retry run started",
    }
