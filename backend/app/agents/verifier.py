"""Agent 3: Eligibility and Verification Agent — checks each opportunity against official sources."""
from __future__ import annotations
import logging
import time
import json
import re
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any
from html.parser import HTMLParser
from html import unescape

import httpx
import fitz
from pydantic import ValidationError

from app.models.student import StudentProfile
from app.models.scholarship import (
    ScholarshipOpportunity, EligibilityAssessment, EligibilityStatus,
    RequirementCheck, VerificationStatus, EvidenceStage
)
from app.models.agent_io import EligibilityResponse
from app.models.workflow import AgentEvent, AgentStatus
from app.agents.state import GraphState
from app.utils.llm import call_llm
from app.utils.search import search_web
from app.utils.event_bus import publish_agent_event

logger = logging.getLogger(__name__)

AGENT_NAME = "eligibility_verifier"


def _is_official_source(url: str, opp: ScholarshipOpportunity) -> bool:
    """Accept provider, university, or public-sector domains as first-party sources."""
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except ValueError:
        return False
    if not host or not (url.startswith("https://") or url.startswith("http://")):
        return False
    labels = set(re.split(r"[^a-z0-9]+", host))
    labels.discard("")
    identity = " ".join(filter(None, [opp.provider, opp.university or ""])).lower()
    identity_tokens = {t for t in re.split(r"[^a-z0-9]+", identity) if len(t) >= 4}
    acronyms = {
        "".join(t[0] for t in re.split(r"[^a-z0-9]+", value.lower()) if t)
        for value in (opp.provider, opp.university or "")
    }
    acronyms = {word for word in acronyms if len(word) >= 3}
    return bool(labels.intersection(identity_tokens | acronyms))


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth and data.strip():
            self.parts.append(data.strip())


_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_EXPLICIT_DATE = re.compile(
    rf"\b(?:\d{{1,2}}\s+{_MONTH}\.?\s+20\d{{2}}|{_MONTH}\s+\d{{1,2}},?\s+20\d{{2}}|"
    r"\d{1,2}[./-]\d{1,2}[./-]20\d{2}|20\d{2}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)


def _deadline_value_is_supported(evidence: Optional[str], required_value: Optional[str]) -> bool:
    """Accept only a specific date value repeated in its official-page quote."""
    if not evidence or not required_value:
        return False
    quote = re.sub(r"\s+", " ", evidence).strip().casefold()
    value = re.sub(r"\s+", " ", required_value).strip().casefold()
    if not value or value in {"unknown", "not stated", "not listed", "specific deadline date"}:
        return False
    return value in quote and bool(_EXPLICIT_DATE.search(evidence))


async def _fetch_official_text(url: str, opp: ScholarshipOpportunity) -> tuple[str, str]:
    """Fetch a live provider page and extract bounded text as citation evidence."""
    if not _is_official_source(url, opp):
        raise ValueError("URL host does not match the named provider or institution")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "ScholarSwarmAI/1.0 (+scholarship verification)"},
    ) as client:
        response = await client.get(url)
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("Official page exceeds the 2 MB verification limit")
    final_url = str(response.url)
    if not _is_official_source(final_url, opp):
        raise ValueError("Official page redirected to a different provider")
    if "pdf" in response.headers.get("content-type", "").lower() or response.content[:4] == b"%PDF":
        with fitz.open(stream=response.content, filetype="pdf") as document:
            page_text = "\n".join(page.get_text() for page in document[:30])
    else:
        parser = _VisibleText()
        parser.feed(response.text)
        page_text = unescape(" ".join(parser.parts))
    page_text = re.sub(r"\s+", " ", page_text).strip()
    if len(page_text) < 80:
        raise ValueError("Official page returned too little readable text")
    return final_url, page_text[:16000]


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


async def _verify_single_opportunity(
    opp: ScholarshipOpportunity,
    profile: StudentProfile,
    on_schema_retry=None,
    on_provider_retry=None,
) -> EligibilityAssessment:
    """Assess an award only against fetched official page text."""
    current_year = time.localtime().tm_year
    query = f'"{opp.name}" {opp.provider} official eligibility requirements international students {current_year}'
    official_pages = []
    search_error = None
    try:
        results = await search_web(query, max_results=5)
        for result in results:
            url = result.get("url", "")
            if not _is_official_source(url, opp):
                continue
            try:
                page_url, page_text = await _fetch_official_text(url, opp)
                official_pages.append({"url": page_url, "title": result.get("title", ""), "text": page_text})
                if len(official_pages) >= 2:
                    break
            except Exception as e:
                logger.info("Official page unavailable for %s (%s)", opp.name, type(e).__name__)
    except Exception as e:
        search_error = f"Official-source search failed: {type(e).__name__}"
        logger.warning("Verification search failed for %s (%s)", opp.name, type(e).__name__)

    if not official_pages:
        opp.official_source_status = EvidenceStage.UNAVAILABLE if search_error else EvidenceStage.UNKNOWN
        opp.requirements_status = EvidenceStage.UNKNOWN
        opp.deadline_status = EvidenceStage.UNKNOWN
        opp.verification_status = VerificationStatus.PARTIAL
        missing = [search_error or "No working official provider page found; requirements not assessed."]
        if not profile.academic.language_scores:
            missing.append("No language test scores were provided; confirm official language requirements.")
        return EligibilityAssessment(
            scholarship_id=opp.id,
            student_id=profile.id,
            status=EligibilityStatus.NEEDS_VERIFICATION,
            confidence=0.0,
            missing_info=missing,
            notes="No eligibility claim made because official page content was unavailable.",
            source_verified=False,
        )

    opp.official_url = official_pages[0]["url"]
    opp.official_source_urls = [page["url"] for page in official_pages]
    opp.official_source_status = EvidenceStage.VERIFIED
    source_text = "\n\n".join(
        f"OFFICIAL PAGE: {page['title']}\nURL: {page['url']}\nPAGE TEXT: {page['text']}"
        for page in official_pages
    )
    profile_summary = json.dumps({
        "nationality": profile.nationality,
        "current_degree": profile.academic.degree_name or profile.academic.major,
        "current_degree_level": profile.academic.degree_level,
        "institution": profile.academic.institution,
        "cgpa": profile.academic.cgpa,
        "cgpa_scale": profile.academic.cgpa_scale,
        "graduation_year": profile.academic.graduation_year,
        "language_scores": profile.academic.language_scores,
        "target_degree": profile.target_degree,
        "target_field": profile.target_field,
        "destinations": profile.destination_preferences,
    }, default=str)
    candidate = json.dumps({
        "name": opp.name,
        "provider": opp.provider,
        "country": opp.country,
        "candidate_source_url": opp.source_url,
    })
    prompt = f"""Evaluate this opportunity only from the fetched official page text below.
Never treat search snippets or candidate fields as proof. Every evidence value must be an exact contiguous quotation (at least 20 characters) copied from official page text, and source_url must be that exact page URL. If the page does not establish a fact, use status unknown and null evidence. Do not infer award amounts, deadlines, citizenship eligibility, degree level, language requirements, GPA equivalence, or funding coverage.

Return checks for each category: opportunity_exists, degree_level, international_eligibility, academic_requirements, language_requirements, field_of_study, funding, deadline. Use not_applicable only with a source quotation that supports it. Use unknown for a deadline not stated on the current page.

Student profile: {profile_summary}
Candidate: {candidate}
Fetched official page text:
{source_text}
"""
    try:
        output = None
        raw = await call_llm(
            prompt, temperature=0.0, max_tokens=1800,
            response_schema=EligibilityResponse,
            on_retry=on_provider_retry,
        )
        for attempt in range(2):
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            try:
                output = EligibilityResponse.model_validate_json(cleaned.strip())
                break
            except ValidationError:
                if attempt:
                    raise
                if on_schema_retry:
                    on_schema_retry()
                raw = await call_llm(
                    prompt + "\nThe previous response failed strict schema validation. Return exactly the required JSON object.",
                    temperature=0.0,
                    max_tokens=1800,
                    response_schema=EligibilityResponse,
                    on_retry=on_provider_retry,
                )

        text_by_url = {page["url"]: page["text"] for page in official_pages}
        checks = []
        for item in output.requirement_checks:
            cited_url = item.source_url if item.source_url in text_by_url else None
            evidence = item.evidence.strip() if item.evidence else None
            status = item.status
            required_value = item.required_value
            if not cited_url or not evidence or len(evidence) < 20:
                cited_url, evidence, status, required_value = None, None, "unknown", None
            else:
                normalized_evidence = re.sub(r"\s+", " ", evidence).casefold()
                normalized_page = re.sub(r"\s+", " ", text_by_url[cited_url]).casefold()
                if normalized_evidence not in normalized_page:
                    cited_url, evidence, status, required_value = None, None, "unknown", None
                else:
                    status = item.status
                    if item.category == "deadline" and not _deadline_value_is_supported(
                        evidence, required_value
                    ):
                        status, required_value = "unknown", None
            checks.append(RequirementCheck(
                category=item.category,
                requirement=item.requirement,
                student_value=item.student_value,
                required_value=required_value,
                status=status,
                evidence=evidence,
                source_url=cited_url,
            ))

        by_category = {check.category: check for check in checks}
        supported = {key for key, check in by_category.items() if check.evidence and check.source_url}
        critical_categories = {
            "opportunity_exists", "degree_level", "international_eligibility",
            "academic_requirements", "language_requirements", "field_of_study", "funding",
        }
        complete_requirements = critical_categories.issubset(supported)
        opp.requirements_status = (
            EvidenceStage.VERIFIED if complete_requirements
            else EvidenceStage.PARTIAL if supported else EvidenceStage.UNKNOWN
        )
        deadline_check = by_category.get("deadline")
        verified_deadline = bool(
            deadline_check
            and deadline_check.evidence
            and deadline_check.source_url
            and _deadline_value_is_supported(
                deadline_check.evidence, deadline_check.required_value
            )
        )
        opp.deadline_status = (
            EvidenceStage.VERIFIED
            if verified_deadline
            else EvidenceStage.UNKNOWN
        )
        exists_check = by_category.get("opportunity_exists")
        funding_check = by_category.get("funding")
        if funding_check and funding_check.evidence:
            opp.funding_description = funding_check.evidence
        else:
            opp.funding_description = ""
            opp.funding_amount_usd = None
            opp.funding_type = opp.funding_type.__class__.UNKNOWN
            opp.covers_tuition = None
            opp.covers_living = None
            opp.covers_travel = None
        academic_check = by_category.get("academic_requirements")
        academic_quote = (academic_check.evidence or "") if academic_check else ""
        if not re.search(r"\b(?:GPA|CGPA)\b", academic_quote, re.IGNORECASE):
            opp.min_cgpa = None
        language_check = by_category.get("language_requirements")
        language_quote = (language_check.evidence or "") if language_check else ""
        opp.required_language_tests = list(dict.fromkeys(re.findall(
            r"\b(?:IELTS|TOEFL|PTE|Duolingo English Test)\b",
            language_quote,
            flags=re.IGNORECASE,
        )))
        degree_check = by_category.get("degree_level")
        degree_quote = (degree_check.evidence or "").casefold() if degree_check else ""
        supported_degrees = []
        if "master" in degree_quote or "msc" in degree_quote or "m.sc" in degree_quote:
            supported_degrees.append("masters")
        if "phd" in degree_quote or "doctoral" in degree_quote or "doctorate" in degree_quote:
            supported_degrees.append("phd")
        if "bachelor" in degree_quote or "undergraduate" in degree_quote:
            supported_degrees.append("bachelors")
        opp.degree_levels = supported_degrees
        opp.open_to_indian_nationals = None
        opp.citizenship_restrictions = []
        if verified_deadline:
            opp.application_deadline = deadline_check.required_value
        else:
            opp.application_deadline = None
            opp.deadline_notes = "No current deadline verified from the official source."
        source_verified = bool(exists_check and exists_check.evidence and exists_check.source_url)
        critical = [by_category.get(category) for category in critical_categories]
        critical_complete = complete_requirements and all(
            item and item.status in {"met", "not_applicable"} for item in critical
        )
        grounded_disqualifier = any(item.status == "not_met" for item in critical if item)
        if grounded_disqualifier:
            status = EligibilityStatus.INELIGIBLE
        elif critical_complete and output.status == "eligible":
            status = EligibilityStatus.ELIGIBLE
        elif supported:
            status = EligibilityStatus.POTENTIALLY_ELIGIBLE
        else:
            status = EligibilityStatus.NEEDS_VERIFICATION
        missing_info = list(output.missing_info)
        if not critical_complete:
            missing_info.append("Critical requirements remain unsupported or unknown in the fetched official source.")
        if opp.deadline_status == EvidenceStage.UNKNOWN:
            missing_info.append("No current deadline was verified; consult the official page.")
        if not profile.academic.language_scores:
            missing_info.append("No language test scores were provided; confirm whether the official requirements need them.")
        if output.status == "eligible" and not critical_complete:
            missing_info.append("The model's eligibility claim was downgraded because critical evidence is incomplete.")
        if source_verified:
            opp.verification_status = VerificationStatus.VERIFIED
        else:
            opp.verification_status = VerificationStatus.PARTIAL
        return EligibilityAssessment(
            scholarship_id=opp.id,
            student_id=profile.id,
            status=status,
            confidence=output.confidence if critical_complete else min(output.confidence, 0.5),
            requirement_checks=checks,
            missing_documents=output.missing_documents,
            missing_info=list(dict.fromkeys(missing_info)),
            disqualifying_factors=output.disqualifying_factors if grounded_disqualifier else [],
            notes=output.notes,
            source_verified=source_verified,
        )
    except Exception as e:
        failure_kind = getattr(e, "failure_kind", "structured_output_failure")
        logger.error("LLM eligibility assessment failed for %s (%s)", opp.name, failure_kind)
        opp.requirements_status = EvidenceStage.PARTIAL
        return EligibilityAssessment(
            scholarship_id=opp.id,
            student_id=profile.id,
            status=EligibilityStatus.NEEDS_VERIFICATION,
            confidence=0.0,
            missing_info=[f"Strict eligibility assessment failed ({failure_kind}); manual review required."],
            notes="No positive eligibility conclusion was accepted.",
            source_verified=False,
        )


async def run_verifier(state: GraphState) -> GraphState:
    """Main verifier agent node."""
    _emit(state, AgentStatus.RUNNING, "Starting eligibility verification for all discovered opportunities")
    start = time.time()

    profile = state.enriched_profile or state.student_profile
    opportunities = state.discovered_opportunities

    if not opportunities:
        _emit(state, AgentStatus.SKIPPED,
              "No opportunities to verify — skipping eligibility assessment")
        state.completed_agents.append(AGENT_NAME)
        return state

    if not profile:
        _emit(state, AgentStatus.FAILED, "No student profile available for eligibility check",
              error="missing_profile")
        return state

    _emit(state, AgentStatus.RUNNING,
          f"Verifying {len(opportunities)} opportunities against student profile and official sources")

    assessments: List[EligibilityAssessment] = []
    verification_errors: List[str] = []
    schema_retries = 0
    provider_retries = 0
    provider_failures = 0
    provider_failure_kinds: Dict[str, int] = {}

    def increment_schema_retries():
        nonlocal schema_retries
        schema_retries += 1

    def increment_provider_retries():
        nonlocal provider_retries
        provider_retries += 1

    for i, opp in enumerate(opportunities):
        _emit(state, AgentStatus.RUNNING,
              f"Verifying [{i + 1}/{len(opportunities)}]: {opp.name} ({opp.country})",
              details={"scholarship_id": opp.id, "scholarship_name": opp.name})
        try:
            assessment = await _verify_single_opportunity(
                opp, profile,
                on_schema_retry=increment_schema_retries,
                on_provider_retry=increment_provider_retries,
            )
            assessments.append(assessment)
            for info in assessment.missing_info:
                if "Strict eligibility assessment failed (" in info:
                    kind = info.split("Strict eligibility assessment failed (", 1)[1].split(")", 1)[0]
                    provider_failures += 1
                    provider_failure_kinds[kind] = provider_failure_kinds.get(kind, 0) + 1

            # Update opportunity verification status
            if not assessment.source_verified:
                opp.verification_status = VerificationStatus.PARTIAL
                verification_errors.append(
                    f"{opp.name}: no fetched official-source quotation verifies the opportunity."
                )
                _emit(state, AgentStatus.FAILED,
                      f"No supported official-source evidence for {opp.name}; retained as needs verification",
                      details={"scholarship_id": opp.id, "official_source_status": opp.official_source_status.value},
                      error="official_source_unverified")
            elif opp.requirements_status != EvidenceStage.VERIFIED:
                verification_errors.append(
                    f"{opp.name}: critical official requirements remain unverified."
                )
                _emit(state, AgentStatus.FAILED,
                      f"Critical requirements remain unverified for {opp.name}",
                      details={
                          "scholarship_id": opp.id,
                          "official_source_status": opp.official_source_status.value,
                          "requirements_status": opp.requirements_status.value,
                          "deadline_status": opp.deadline_status.value,
                      },
                      error="requirements_incomplete")

            _emit(state, AgentStatus.RUNNING,
                  f"Verified {opp.name}: {assessment.status.value} "
                  f"(confidence: {int(assessment.confidence * 100)}%)",
                  details={
                      "status": assessment.status.value,
                      "confidence": assessment.confidence,
                      "missing_docs": assessment.missing_documents,
                      "official_source_urls": [opp.official_url] if assessment.source_verified and opp.official_url else [],
                      "official_source_status": opp.official_source_status.value,
                      "requirements_status": opp.requirements_status.value,
                      "eligibility_status": assessment.status.value,
                      "deadline_status": opp.deadline_status.value,
                  })
        except Exception as e:
            logger.error(f"Verification failed for {opp.name}: {e}")
            verification_errors.append(f"{opp.name}: {str(e)[:100]}")
            # Add a failed assessment — do not skip silently
            assessments.append(EligibilityAssessment(
                scholarship_id=opp.id,
                student_id=profile.id,
                status=EligibilityStatus.NEEDS_VERIFICATION,
                confidence=0.2,
                missing_info=["Verification process encountered an error"],
                notes=f"Error during verification: {str(e)[:100]}",
            ))
            _emit(state, AgentStatus.RETRYING,
                  f"Verification error for {opp.name} — marked as needs_verification",
                  error=str(e))

    duration_ms = int((time.time() - start) * 1000)

    eligible_count = sum(1 for a in assessments if a.status == EligibilityStatus.ELIGIBLE)
    potential_count = sum(1 for a in assessments if a.status == EligibilityStatus.POTENTIALLY_ELIGIBLE)
    needs_check = sum(1 for a in assessments if a.status == EligibilityStatus.NEEDS_VERIFICATION)
    ineligible_count = sum(1 for a in assessments if a.status == EligibilityStatus.INELIGIBLE)
    source_count = sum(1 for o in opportunities if o.official_source_status == EvidenceStage.VERIFIED)
    requirements_count = sum(1 for o in opportunities if o.requirements_status == EvidenceStage.VERIFIED)
    deadlines_count = sum(1 for o in opportunities if o.deadline_status == EvidenceStage.VERIFIED)

    state.eligibility_assessments = assessments
    state.verification_errors = verification_errors
    state.completed_agents.append(AGENT_NAME)

    _emit(state, AgentStatus.COMPLETED,
          f"Eligibility verification complete: {eligible_count} eligible, "
          f"{potential_count} potentially eligible, {needs_check} needs verification, "
          f"{ineligible_count} ineligible",
          details={
              "schema_retries": schema_retries,
              "provider_retries": provider_retries,
              "provider_failures": provider_failures,
              "provider_failure_kinds": provider_failure_kinds,
              "official_sources_located": source_count,
              "requirements_verified": requirements_count,
              "deadlines_verified": deadlines_count,
              "eligible": eligible_count,
              "potentially_eligible": potential_count,
              "needs_verification": needs_check,
              "ineligible": ineligible_count,
              "errors": len(verification_errors),
          })
    state.events[-1].duration_ms = duration_ms
    return state
