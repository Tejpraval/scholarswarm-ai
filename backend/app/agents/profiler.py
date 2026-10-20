"""Agent 1: Student Profiler — enriches and validates the student profile."""
from __future__ import annotations
import logging
import time
import json
from typing import Optional, Dict, Any
from datetime import datetime

import httpx

from app.models.student import StudentProfile, AcademicProfile
from app.models.workflow import AgentEvent, AgentStatus
from app.agents.state import GraphState
from app.utils.llm import call_llm
from app.utils.pdf_extractor import extract_text_from_path
from app.utils.event_bus import publish_agent_event

logger = logging.getLogger(__name__)

AGENT_NAME = "student_profiler"


def _emit(state: GraphState, status: AgentStatus, message: str,
          details: Optional[Dict] = None, error: Optional[str] = None) -> AgentEvent:
    ev = AgentEvent(
        run_id=state.run_id,
        agent_name=AGENT_NAME,
        status=status,
        message=message,
        details=details,
        error=error,
    )
    state.events.append(ev)
    publish_agent_event(ev)
    logger.info(f"[{AGENT_NAME}] {status.value}: {message}")
    return ev


def _compute_completeness(profile: StudentProfile) -> tuple[float, list[str]]:
    """Return (completeness_0_to_1, list_of_missing_fields)."""
    fields = {
        "name": bool(profile.name),
        "nationality": bool(profile.nationality),
        "degree_level": bool(profile.academic.degree_level),
        "institution": bool(profile.academic.institution),
        "cgpa": profile.academic.cgpa is not None,
        "graduation_year": bool(profile.academic.graduation_year),
        "skills": len(profile.skills) > 0,
        "destination_preferences": len(profile.destination_preferences) > 0,
        "target_degree": bool(profile.target_degree),
        "language_scores": bool(profile.academic.language_scores),
        "github_url": bool(profile.github_url),
    }
    missing = [k for k, v in fields.items() if not v]
    completeness = sum(1 for v in fields.values() if v) / len(fields)
    return round(completeness, 2), missing


async def _fetch_github_profile(github_url: str) -> Optional[Dict[str, Any]]:
    """Fetch public GitHub profile data. Returns None on failure."""
    try:
        # Extract username from URL
        username = github_url.rstrip("/").split("/")[-1]
        if not username:
            return None
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.github.com/users/{username}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                logger.warning(f"GitHub API returned {resp.status_code} for {username}")
                return None
            user_data = resp.json()

            # Also fetch repos
            repos_resp = await client.get(
                f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            repos = repos_resp.json() if repos_resp.status_code == 200 else []

        # Summarise
        languages = {}
        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

        return {
            "username": username,
            "name": user_data.get("name"),
            "bio": user_data.get("bio"),
            "public_repos": user_data.get("public_repos", 0),
            "followers": user_data.get("followers", 0),
            "top_languages": sorted(languages, key=languages.get, reverse=True)[:5],
            "repos_summary": [
                {
                    "name": r.get("name"),
                    "description": r.get("description"),
                    "language": r.get("language"),
                    "stars": r.get("stargazers_count", 0),
                }
                for r in repos[:5]
            ],
            "profile_url": user_data.get("html_url"),
        }
    except Exception as e:
        logger.warning(f"GitHub fetch failed: {e}")
        return None


async def _extract_profile_from_documents(profile: StudentProfile) -> Dict[str, Any]:
    """Extract structured info from uploaded resume/marksheet PDFs."""
    extracted_info: Dict[str, Any] = {}
    for doc in profile.documents:
        if doc.extraction_status == "done" and doc.extracted_text:
            text = doc.extracted_text
            prompt = f"""You are a student profile extractor. Given the following text extracted from a student's {doc.doc_type.value},
extract structured information and return ONLY a valid JSON object with these fields (use null for unknown):
{{
  "name": null,
  "degree_level": null,
  "degree_name": null,
  "institution": null,
  "cgpa": null,
  "cgpa_scale": null,
  "graduation_year": null,
  "major": null,
  "skills": [],
  "achievements": [],
  "projects": [],
  "language_scores": {{}}
}}

Document text:
{text[:3000]}

Return only the JSON object, no explanation."""
            try:
                result = await call_llm(prompt, temperature=0.1, max_tokens=1000)
                parsed = json.loads(result.strip().strip("```json").strip("```").strip())
                extracted_info.update({k: v for k, v in parsed.items() if v})
            except Exception as e:
                logger.warning(f"LLM extraction from {doc.doc_type.value} failed: {e}")
    return extracted_info


def _merge_extracted_into_profile(profile: StudentProfile, extracted: Dict[str, Any]) -> StudentProfile:
    """Merge LLM-extracted fields into the profile without overwriting user-provided data."""
    # Use model_dump to get a plain dict (datetimes become strings via mode="json")
    data = profile.model_dump(mode="json")

    # Academic fields
    academic = data["academic"]
    if not academic.get("cgpa") and extracted.get("cgpa"):
        try:
            academic["cgpa"] = float(extracted["cgpa"])
        except (TypeError, ValueError):
            pass
    if not academic.get("institution") and extracted.get("institution"):
        academic["institution"] = extracted["institution"]
    if not academic.get("graduation_year") and extracted.get("graduation_year"):
        try:
            academic["graduation_year"] = int(extracted["graduation_year"])
        except (TypeError, ValueError):
            pass
    if not academic.get("language_scores") and extracted.get("language_scores"):
        academic["language_scores"] = extracted["language_scores"]
    data["academic"] = academic

    # Top-level fields
    if not data.get("name") and extracted.get("name"):
        data["name"] = extracted["name"]

    # Merge lists without duplicating
    existing_skills = set(data.get("skills", []))
    for s in extracted.get("skills", []):
        existing_skills.add(s)
    data["skills"] = list(existing_skills)

    existing_achievements = set(data.get("achievements", []))
    for a in extracted.get("achievements", []):
        existing_achievements.add(a)
    data["achievements"] = list(existing_achievements)

    data["extracted_from_documents"] = True
    return StudentProfile(**data)


async def run_profiler(state: GraphState) -> GraphState:
    """Main profiler agent node."""
    _emit(state, AgentStatus.RUNNING, "Starting student profile validation and enrichment")
    start = time.time()

    profile = state.student_profile
    if not profile:
        _emit(state, AgentStatus.FAILED, "No student profile provided", error="missing_profile")
        state.workflow_error = "Student profile is required to proceed."
        return state

    # Step 1: Extract from uploaded documents
    _emit(state, AgentStatus.RUNNING, "Extracting information from uploaded documents")
    try:
        extracted = await _extract_profile_from_documents(profile)
        if extracted:
            profile = _merge_extracted_into_profile(profile, extracted)
            _emit(state, AgentStatus.RUNNING,
                  f"Extracted {len(extracted)} fields from uploaded documents",
                  details={"extracted_keys": list(extracted.keys())})
    except Exception as e:
        logger.warning(f"Document extraction partial failure: {e}")
        _emit(state, AgentStatus.RUNNING,
              "Document extraction encountered issues; proceeding with provided profile",
              error=str(e))

    # Step 2: GitHub enrichment
    if profile.github_url:
        _emit(state, AgentStatus.RUNNING,
              f"Fetching public GitHub profile: {profile.github_url}")
        github_data = await _fetch_github_profile(profile.github_url)
        if github_data:
            profile = profile.model_copy(update={
                "github_enrichment": github_data
            })
            # Merge discovered languages into skills
            for lang in github_data.get("top_languages", []):
                if lang not in profile.skills:
                    profile.skills.append(lang)
            state.github_data = github_data
            _emit(state, AgentStatus.RUNNING,
                  f"GitHub profile fetched: {github_data.get('public_repos', 0)} public repos, "
                  f"top languages: {github_data.get('top_languages', [])}",
                  details={"github": github_data})
        else:
            _emit(state, AgentStatus.RUNNING,
                  "GitHub profile unavailable or not found — proceeding without GitHub enrichment")

    # Step 3: Compute completeness
    completeness, missing = _compute_completeness(profile)
    profile = profile.model_copy(update={
        "profile_completeness": completeness,
        "missing_fields": missing,
        "updated_at": datetime.utcnow(),
    })

    duration_ms = int((time.time() - start) * 1000)
    state.enriched_profile = profile
    state.profile_validated = True
    state.profile_issues = missing
    state.completed_agents.append(AGENT_NAME)

    _emit(state, AgentStatus.COMPLETED,
          f"Profile enriched. Completeness: {int(completeness * 100)}%. "
          f"Missing fields: {missing if missing else 'none'}",
          details={
              "completeness": completeness,
              "missing_fields": missing,
              "skills_count": len(profile.skills),
              "documents_count": len(profile.documents),
              "github_enriched": state.github_data is not None,
          },
          )
    # Update duration on last event
    state.events[-1].duration_ms = duration_ms
    return state
