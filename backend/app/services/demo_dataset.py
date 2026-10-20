"""Build deterministic, explicitly curated demonstration results.

This code never calls Gemini, Tavily, or the LangGraph live workflow.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.matcher import _generate_sop, _is_recommendable, _score_opportunity
from app.agents.state import GraphState
from app.models.application import ApplicationDraft
from app.models.scholarship import (
    EligibilityAssessment,
    EligibilityStatus,
    MatchResult,
    ScholarshipOpportunity,
)
from app.models.student import StudentProfile

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "demo_fixture" / "opportunities.json"


def load_fixture() -> dict[str, Any]:
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def validate_demo_profile(profile: StudentProfile, fixture: dict[str, Any]) -> list[str]:
    """Require the documented fictional qualifications before applying its assessment."""
    expected = fixture["demo_profile"]
    missing = []
    if (profile.nationality or "").casefold() != expected["nationality"].casefold():
        missing.append("the curated demo nationality (Indian)")
    if (profile.academic.degree_level.value if profile.academic.degree_level else None) != expected["degree_level"]:
        missing.append("the curated demo bachelor's degree level")
    if (profile.academic.degree_name or "").casefold() != expected["degree_name"].casefold():
        missing.append("the curated demo completed degree")
    if profile.academic.graduation_year != expected["graduation_year"]:
        missing.append("the curated demo graduation year")
    if (profile.target_degree.value if profile.target_degree else None) != expected["target_degree"]:
        missing.append("a Master's target degree")
    if not any(country.casefold() == "australia" for country in profile.destination_preferences):
        missing.append("Australia as a selected destination")

    notes = profile.personal_statement_notes or ""
    for fact in (
        "unconditional offer for full-time CRICOS-registered coursework Master's study at the University of Sydney commencing Semester 1 2027",
        "has not commenced that course",
        "is not receiving an Australian Government scholarship",
    ):
        if fact.casefold() not in notes.casefold():
            missing.append(f"the documented fictional fact: {fact}")
    return missing


async def build_demo_state(run_id: str, profile: StudentProfile) -> tuple[GraphState, dict[str, Any]]:
    fixture = load_fixture()
    missing_facts = validate_demo_profile(profile, fixture)
    if missing_facts:
        raise ValueError(
            "This curated fixture assesses only its documented fictional profile. "
            "Restore the curated qualifications or choose Live Research. Missing: "
            + "; ".join(missing_facts)
        )

    state = GraphState(run_id=run_id, student_id=profile.id, student_profile=profile)
    opportunities: list[ScholarshipOpportunity] = []
    assessments: list[EligibilityAssessment] = []
    for item in fixture["opportunities"]:
        opp_data = {key: value for key, value in item.items() if key not in {"eligibility", "provenance"}}
        opp_data["retrieved_at"] = datetime.fromisoformat(fixture["verified_on"])
        opp = ScholarshipOpportunity.model_validate(opp_data)
        elig_data = item["eligibility"]
        assessment = EligibilityAssessment(
            scholarship_id=opp.id,
            student_id=profile.id,
            status=EligibilityStatus(elig_data["status"]),
            confidence=elig_data["confidence"],
            requirement_checks=elig_data["checks"],
            missing_info=elig_data["missing_info"],
            notes=elig_data["notes"],
            source_verified=opp.official_source_status.value == "verified",
            eligibility_assessed=True,
        )
        opportunities.append(opp)
        assessments.append(assessment)

    assessed = {assessment.scholarship_id: assessment for assessment in assessments}
    scored = [
        (_score_opportunity(opp, assessed[opp.id], profile), opp, assessed[opp.id])
        for opp in opportunities
    ]
    scored.sort(key=lambda row: (-row[0][0], row[1].name.casefold(), row[1].id))
    matches = []
    for rank, ((score, breakdown), opp, assessment) in enumerate(scored, start=1):
        matches.append(MatchResult(
            scholarship_id=opp.id,
            student_id=profile.id,
            rank=rank,
            match_score=score,
            eligibility_status=assessment.status,
            eligibility_confidence=assessment.confidence,
            score_breakdown=breakdown,
            match_explanation=(
                "Deterministic match score: eligibility confidence, funding, destination, "
                "field, academic fit, and deadline. Score is separate from eligibility."
            ),
            why_recommended=(
                "Confirmed against the curated official-source evidence for this fictional demo profile."
                if assessment.status == EligibilityStatus.ELIGIBLE
                else "Not confirmed: review the unresolved requirements shown in the eligibility checklist."
            ),
            scholarship=opp,
            eligibility=assessment,
            missing_requirements=assessment.missing_info,
            next_actions=assessment.missing_info + [f"Review the official source: {opp.official_url}"],
        ))

    top_matches = [match for match in matches if _is_recommendable(match, profile)][:5]
    sop: ApplicationDraft | None = None
    if top_matches and top_matches[0].scholarship:
        sop = await _generate_sop(top_matches[0].scholarship, profile, run_id)
        sop.warnings.insert(
            0,
            "Curated demo draft: it uses the fictional demonstration profile, not live AI research or a real applicant's record.",
        )

    state.discovered_opportunities = opportunities
    state.eligibility_assessments = assessments
    state.match_results = matches
    state.top_matches = top_matches
    state.sop_draft = sop
    return state, fixture
