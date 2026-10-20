"""Agent 4: Matching and Application Agent — ranks opportunities and drafts an SOP."""
from __future__ import annotations
import logging
import time
import json
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date

from app.models.student import StudentProfile
from app.models.scholarship import (
    ScholarshipOpportunity, EligibilityAssessment, MatchResult,
    EligibilityStatus, FundingType, EvidenceStage
)
from app.models.workflow import AgentEvent, AgentStatus
from app.models.application import ApplicationDraft
from app.agents.state import GraphState
from app.utils.llm import call_llm
from app.utils.event_bus import publish_agent_event
from app.utils.dates import deadline_is_current

logger = logging.getLogger(__name__)

AGENT_NAME = "matching_agent"
TOP_N = 5


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


def _score_opportunity(
    opp: ScholarshipOpportunity,
    assessment: EligibilityAssessment,
    profile: StudentProfile
) -> Tuple[float, Dict[str, float]]:
    """
    Transparent scoring model. Returns (total_score, breakdown).
    Max score = 100.
    NOTE: A high score does NOT imply confirmed eligibility.
    """
    breakdown: Dict[str, float] = {}

    # 1. Eligibility confidence (30 pts)
    eligibility_map = {
        EligibilityStatus.ELIGIBLE: 30.0,
        EligibilityStatus.POTENTIALLY_ELIGIBLE: 20.0,
        EligibilityStatus.NEEDS_VERIFICATION: 12.0,
        EligibilityStatus.INELIGIBLE: 0.0,
    }
    eligibility_score = eligibility_map.get(assessment.status, 10.0)
    eligibility_score *= assessment.confidence
    breakdown["eligibility_confidence"] = round(eligibility_score, 1)

    # 2. Funding coverage match (25 pts)
    funding_score = 0.0
    full_funding_types = {FundingType.FULL}
    if opp.funding_type in full_funding_types:
        funding_score = 25.0
    elif opp.funding_type == FundingType.PARTIAL:
        funding_score = 12.0
    elif opp.funding_type in {FundingType.TUITION, FundingType.STIPEND}:
        funding_score = 8.0
    elif opp.funding_type == FundingType.LIVING:
        funding_score = 6.0
    else:
        funding_score = 3.0

    # Extra weight if student needs full funding
    if profile.funding_preference.value == "full_funding" and opp.funding_type == FundingType.FULL:
        funding_score = min(funding_score * 1.2, 25.0)
    breakdown["funding_match"] = round(funding_score, 1)

    # 3. Destination preference (15 pts)
    dest_score = 0.0
    if opp.country and profile.destination_preferences:
        for pref in profile.destination_preferences:
            if pref.lower() in opp.country.lower() or opp.country.lower() in pref.lower():
                dest_score = 15.0
                break
            # Partial: same region
            region_map = {
                "canada": ["north america"],
                "germany": ["europe", "eu"],
                "singapore": ["southeast asia", "asia"],
            }
            for pref_key, regions in region_map.items():
                if pref_key in pref.lower() and any(r in opp.country.lower() for r in regions):
                    dest_score = max(dest_score, 5.0)
    breakdown["destination_preference"] = round(dest_score, 1)

    # 4. Academic field alignment (15 pts)
    field_score = 0.0
    student_field = (profile.target_field or "").lower()
    student_skills = [s.lower() for s in profile.skills]
    opp_fields = [f.lower() for f in opp.fields_of_study]
    opp_text = " ".join(opp_fields + [opp.name.lower()])

    ai_keywords = ["artificial intelligence", "machine learning", "computer science",
                   "data science", "ai", "ml", "nlp", "deep learning", "computer vision"]
    keyword_hits = sum(1 for kw in ai_keywords if kw in opp_text or kw in student_field)
    field_score = min(keyword_hits * 3.0, 15.0)
    breakdown["field_alignment"] = round(field_score, 1)

    # 5. CGPA fit (10 pts)
    cgpa_score = 10.0  # default: no CGPA requirement stated = no penalty
    if opp.min_cgpa and profile.academic.cgpa:
        # Normalise to same scale
        student_cgpa_pct = profile.academic.cgpa / (profile.academic.cgpa_scale or 10.0)
        req_cgpa_scale = 4.0 if opp.min_cgpa <= 4.0 else 10.0
        req_cgpa_pct = opp.min_cgpa / req_cgpa_scale
        if student_cgpa_pct >= req_cgpa_pct:
            cgpa_score = 10.0
        elif student_cgpa_pct >= req_cgpa_pct * 0.9:
            cgpa_score = 5.0
        else:
            cgpa_score = 0.0
    elif opp.min_cgpa and not profile.academic.cgpa:
        cgpa_score = 4.0  # Unknown — penalize slightly
    breakdown["cgpa_fit"] = round(cgpa_score, 1)

    # 6. Deadline feasibility (5 pts)
    deadline_score = 5.0
    if opp.application_deadline:
        try:
            # Try to parse deadline
            dl_str = opp.application_deadline
            for fmt in ["%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y"]:
                try:
                    dl = datetime.strptime(dl_str, fmt).date()
                    today = date.today()
                    days_remaining = (dl - today).days
                    if days_remaining < 0:
                        deadline_score = 0.0  # Passed
                    elif days_remaining < 30:
                        deadline_score = 2.0  # Very tight
                    elif days_remaining < 90:
                        deadline_score = 4.0
                    else:
                        deadline_score = 5.0
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    breakdown["deadline_feasibility"] = round(deadline_score, 1)

    total = sum(breakdown.values())
    return round(total, 1), breakdown


def _is_recommendable(result: MatchResult, profile: StudentProfile) -> bool:
    """Require source-backed requirements and a confirmed profile fit."""
    assessment = result.eligibility
    scholarship = result.scholarship
    if not scholarship or scholarship.official_source_status != EvidenceStage.VERIFIED:
        return False
    if scholarship.requirements_status != EvidenceStage.VERIFIED:
        return False
    if scholarship.deadline_status not in {EvidenceStage.VERIFIED, EvidenceStage.UNKNOWN}:
        return False
    if scholarship.deadline_status == EvidenceStage.VERIFIED and deadline_is_current(
        scholarship.application_deadline
    ) is not True:
        return False
    if result.eligibility_status != EligibilityStatus.ELIGIBLE or not assessment:
        return False
    preferences = [p.strip().casefold() for p in profile.destination_preferences if p.strip()]
    country = (scholarship.country or "").strip().casefold()
    if preferences and (not country or not any(
        pref in country or country in pref for pref in preferences
    )):
        return False
    target_degree = (profile.target_degree or "").casefold()
    degree_aliases = {
        "master": {"master", "masters", "master's", "msc", "ma", "mtech", "meng"},
        "phd": {"phd", "ph.d", "doctoral", "doctorate"},
        "bachelor": {"bachelor", "bachelors", "undergraduate", "bsc", "ba", "btech"},
    }
    target_kind = next((kind for kind, aliases in degree_aliases.items()
                        if target_degree in aliases or any(alias in target_degree for alias in aliases)), None)
    levels = {level.strip().casefold() for level in scholarship.degree_levels}
    if target_kind and not any(
        level in degree_aliases[target_kind] or any(alias in level for alias in degree_aliases[target_kind])
        for level in levels
    ):
        return False
    critical_categories = {
        "opportunity_exists", "degree_level", "international_eligibility",
        "academic_requirements", "language_requirements", "field_of_study", "funding",
    }
    checks_by_category = {check.category: check for check in assessment.requirement_checks}
    for category in critical_categories:
        check = checks_by_category.get(category)
        if not check or check.status not in {"met", "not_applicable"}:
            return False
        if not check.evidence or not check.source_url or check.source_url not in (
            scholarship.official_source_urls or [scholarship.official_url]
        ):
            return False
    if assessment.disqualifying_factors:
        return False
    if any(check.status == "not_met" for check in assessment.requirement_checks):
        return False
    # Different names for the same award (for example, an award name with and
    # without "Foundation") must not inflate the highlighted match count.
    return True


def _recommendation_key(result: MatchResult) -> str:
    name = result.scholarship.name if result.scholarship else result.scholarship_id
    return re.sub(r"[^a-z0-9]", "", name.casefold().replace("foundation", ""))


async def _generate_sop(
    opp: ScholarshipOpportunity,
    profile: StudentProfile,
    run_id: str
) -> ApplicationDraft:
    """Build a conservative SOP draft without allowing unsupported personal claims."""
    facts_available = []
    placeholders = []
    warnings = []
    paragraphs = ["Dear Admissions Committee,", ""]

    if profile.name:
        facts_available.append(f"Name: {profile.name}")
        paragraphs.append(f"My name is {profile.name}.")
    else:
        placeholders.append("FULL_NAME")
        paragraphs.append("My name is [FULL_NAME].")

    academic_parts = []
    if profile.academic.degree_name:
        academic_parts.append(profile.academic.degree_name)
        facts_available.append(f"Degree: {profile.academic.degree_name}")
    if profile.academic.institution:
        academic_parts.append(f"at {profile.academic.institution}")
        facts_available.append(f"Institution: {profile.academic.institution}")
    if academic_parts:
        paragraphs.append("My academic background is " + " ".join(academic_parts) + ".")
    else:
        placeholders.append("ACADEMIC_BACKGROUND")
        paragraphs.append("My academic background is [ACADEMIC_BACKGROUND].")

    if profile.academic.cgpa is not None:
        scale = profile.academic.cgpa_scale or 10.0
        paragraphs.append(f"My reported CGPA is {profile.academic.cgpa}/{scale}.")
        facts_available.append(f"CGPA: {profile.academic.cgpa}/{scale}")

    if profile.skills:
        skills = ", ".join(profile.skills[:10])
        paragraphs.append(f"The skills I have listed include {skills}.")
        facts_available.append(f"Skills: {skills}")

    if profile.projects:
        names = [str(project.get("name", "")).strip() for project in profile.projects[:3]]
        names = [name for name in names if name]
        if names:
            paragraphs.append("Projects listed in my profile include " + "; ".join(names) + ".")
            facts_available.extend(f"Project: {name}" for name in names)

    if profile.research_interests:
        interests = ", ".join(profile.research_interests)
        paragraphs.append(f"My stated research interests are {interests}.")
        facts_available.append(f"Research interests: {interests}")

    if profile.achievements:
        achievements = [str(value).strip() for value in profile.achievements[:3] if str(value).strip()]
        if achievements:
            paragraphs.append("Achievements listed in my profile include " + "; ".join(achievements) + ".")
            facts_available.extend(f"Achievement: {value}" for value in achievements)

    paragraphs.extend([
        "",
        "I am interested in pursuing further study in the area described in my application. "
        "I will tailor this statement to the specific programme after confirming its official requirements.",
    ])
    if not profile.academic.language_scores:
        placeholders.append("LANGUAGE_TEST_AND_SCORE_IF_REQUIRED")
        warnings.append("No language test scores were provided; confirm the programme requirement.")
        paragraphs.append("Language test information: [LANGUAGE_TEST_AND_SCORE_IF_REQUIRED].")
    if not profile.work_experience:
        placeholders.append("RELEVANT_EXPERIENCE_IF_ANY")
        paragraphs.append("Relevant experience: [RELEVANT_EXPERIENCE_IF_ANY].")

    placeholders.extend(["PROGRAMME_SPECIFIC_MOTIVATION", "CAREER_GOALS"])
    paragraphs.extend([
        "My reasons for choosing this programme are [PROGRAMME_SPECIFIC_MOTIVATION].",
        "My future academic and career goals are [CAREER_GOALS].",
        "",
        "Thank you for considering my application.",
        "",
        "--- DRAFT ONLY ? Complete every [PLACEHOLDER] and verify programme details before submission. ---",
    ])
    draft_text = "\n".join(paragraphs)
    return ApplicationDraft(
        run_id=run_id,
        student_id=profile.id,
        scholarship_id=opp.id,
        scholarship_name=opp.name,
        university=opp.university,
        draft_text=draft_text,
        placeholders=placeholders,
        word_count=len(draft_text.split()),
        is_draft=True,
        facts_used=facts_available,
        warnings=warnings,
    )


async def run_matcher(state: GraphState) -> GraphState:
    """Main matching and application agent node."""
    _emit(state, AgentStatus.RUNNING, "Starting opportunity ranking and match scoring")
    start = time.time()

    profile = state.enriched_profile or state.student_profile
    opportunities = state.discovered_opportunities
    assessments = state.eligibility_assessments

    if not opportunities:
        _emit(state, AgentStatus.SKIPPED, "No opportunities to rank")
        state.completed_agents.append(AGENT_NAME)
        return state

    if not profile:
        _emit(state, AgentStatus.FAILED, "No student profile available",
              error="missing_profile")
        return state

    # Build assessment lookup
    assessment_map: Dict[str, EligibilityAssessment] = {
        a.scholarship_id: a for a in assessments
    }

    # Score all opportunities
    _emit(state, AgentStatus.RUNNING,
          f"Scoring {len(opportunities)} opportunities using transparent scoring model")

    scored: List[Tuple[float, ScholarshipOpportunity, EligibilityAssessment]] = []
    for opp in opportunities:
        assessment = assessment_map.get(opp.id)
        if not assessment:
            # Create a default assessment for unverified opportunities
            assessment = EligibilityAssessment(
                scholarship_id=opp.id,
                student_id=profile.id,
                status=EligibilityStatus.NEEDS_VERIFICATION,
                confidence=0.3,
                missing_info=["Not assessed by verifier"],
                notes="Verification was not performed for this opportunity.",
            )
        score, breakdown = _score_opportunity(opp, assessment, profile)
        scored.append((score, opp, assessment))

    # Sort by score descending
    scored.sort(key=lambda x: (-x[0], x[1].name.casefold(), x[1].id))

    # Create MatchResult objects for all
    all_results: List[MatchResult] = []
    for rank, (score, opp, assessment) in enumerate(scored, 1):
        _, breakdown = _score_opportunity(opp, assessment, profile)

        next_actions = []
        if not profile.academic.language_scores:
            next_actions.append("Take and report IELTS or TOEFL test scores")
        if assessment.missing_documents:
            next_actions.extend([f"Prepare: {doc}" for doc in assessment.missing_documents[:3]])
        if opp.official_url:
            next_actions.append(f"Review official requirements at {opp.official_url}")
        if opp.application_deadline:
            next_actions.append(f"Application deadline: {opp.application_deadline}")

        result = MatchResult(
            scholarship_id=opp.id,
            student_id=profile.id,
            rank=rank,
            match_score=score,
            eligibility_status=assessment.status,
            eligibility_confidence=assessment.confidence,
            score_breakdown=breakdown,
            match_explanation=f"Score {score}/100 based on eligibility ({breakdown.get('eligibility_confidence', 0)}), funding ({breakdown.get('funding_match', 0)}), destination ({breakdown.get('destination_preference', 0)}), field alignment ({breakdown.get('field_alignment', 0)}), CGPA fit ({breakdown.get('cgpa_fit', 0)}), deadline ({breakdown.get('deadline_feasibility', 0)})",
            scholarship=opp,
            eligibility=assessment,
            missing_requirements=assessment.missing_documents + assessment.missing_info,
            next_actions=next_actions,
        )
        all_results.append(result)

    # A high match score is not proof that an opportunity is suitable. Only
    # source-verified opportunities with no confirmed disqualifier are promoted.
    top5 = []
    seen_recommendations = set()
    for result in all_results:
        if not _is_recommendable(result, profile):
            continue
        key = _recommendation_key(result)
        if key in seen_recommendations:
            continue
        seen_recommendations.add(key)
        top5.append(result)
        if len(top5) == TOP_N:
            break

    # Generate why_recommended for top 5 using LLM
    _emit(state, AgentStatus.RUNNING, f"Generating recommendation explanations for top {TOP_N} matches")
    for result in top5:
        opp = result.scholarship
        assessment = result.eligibility
        if opp and assessment:
            try:
                prompt = f"""In 2-3 sentences, explain why this scholarship is recommended for this student.
Be specific, factual, and based only on the information below. Do NOT invent facts.

Student: {profile.name}, {profile.academic.degree_name or 'B.Tech CS'} with {profile.academic.cgpa or 'N/A'} CGPA,
interested in {profile.target_field or 'AI/ML'}, needs {profile.funding_preference.value},
prefers: {', '.join(profile.destination_preferences) if profile.destination_preferences else 'N/A'}

Scholarship: {opp.name} by {opp.provider} in {opp.country}
Funding: {opp.funding_description or opp.funding_type.value}
Eligibility: {assessment.status.value} (confidence: {int(assessment.confidence*100)}%)
Score: {result.match_score}/100

Write a clear, honest 2-3 sentence recommendation explanation."""
                explanation = await call_llm(prompt, temperature=0.3, max_tokens=200)
                result.why_recommended = explanation.strip()
            except Exception as e:
                logger.warning(f"Explanation generation failed: {e}")
                result.why_recommended = (
                    f"Recommended based on match score of {result.match_score}/100. "
                    f"Eligibility: {assessment.status.value}. "
                    f"Destination preference and funding type align with student requirements."
                )

    # Generate SOP for the strongest non-ineligible opportunity
    sop_candidate = top5[0] if top5 else None
    if sop_candidate and sop_candidate.scholarship:
        _emit(state, AgentStatus.RUNNING,
              f"Drafting Statement of Purpose for: {sop_candidate.scholarship.name}")
        sop = await _generate_sop(sop_candidate.scholarship, profile, state.run_id)
        state.sop_draft = sop
        _emit(state, AgentStatus.RUNNING,
              f"SOP draft generated: {sop.word_count} words, {len(sop.placeholders)} placeholders to fill",
              details={"word_count": sop.word_count, "placeholders": sop.placeholders})

    duration_ms = int((time.time() - start) * 1000)

    state.match_results = all_results
    state.top_matches = top5
    state.completed_agents.append(AGENT_NAME)

    _emit(state, AgentStatus.COMPLETED,
          f"Matching complete: {len(all_results)} ranked, top {len(top5)} highlighted, SOP drafted",
          details={
              "total_ranked": len(all_results),
              "top_matches": len(top5),
              "sop_generated": state.sop_draft is not None,
              "top_scholarship": top5[0].scholarship.name if top5 and top5[0].scholarship else None,
          })
    state.events[-1].duration_ms = duration_ms
    return state
