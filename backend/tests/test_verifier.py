"""Tests for the Eligibility and Verification Agent."""
import pytest
from unittest.mock import AsyncMock, patch

from app.agents.state import GraphState
from app.agents.verifier import run_verifier, _is_official_source, _deadline_value_is_supported
from app.utils.dates import deadline_is_current
from app.models.student import DEMO_PROFILE, StudentProfile, AcademicProfile, DegreeLevel
from app.models.scholarship import (
    ScholarshipOpportunity, EligibilityAssessment, EligibilityStatus,
    FundingType, SourceType, RequirementCheck
)
from app.models.workflow import AgentStatus


SAMPLE_OPPORTUNITY = ScholarshipOpportunity(
    id="test-opp-1",
    name="Test Graduate Scholarship",
    provider="Test University",
    source_type=SourceType.UNIVERSITY,
    country="Canada",
    degree_levels=["masters"],
    fields_of_study=["Computer Science"],
    funding_type=FundingType.FULL,
    min_cgpa=7.0,
    required_language_tests=["IELTS"],
    open_to_indian_nationals=True,
    source_url="https://example.com/scholarship",
)

OFFICIAL_PAGE_URL = "https://test.edu/scholarship"
OFFICIAL_PAGE_TEXT = (
    "Test Graduate Scholarship provides scholarships to international students "
    "enrolled in a master's degree in Computer Science at Test University. "
    "Awards provide full tuition. Applicants must have IELTS 6.5. "
    "The application deadline is 30 June 2027. Minimum CGPA 7.0 on a 10 point scale."
)

MOCK_ELIGIBLE_ASSESSMENT = {
    "status": "eligible",
    "confidence": 0.9,
    "requirement_checks": [
        {"category": "opportunity_exists", "requirement": "Award exists", "status": "met", "evidence": "Test Graduate Scholarship provides scholarships", "source_url": OFFICIAL_PAGE_URL},
        {"category": "degree_level", "requirement": "Degree level", "status": "met", "evidence": "enrolled in a master's degree", "source_url": OFFICIAL_PAGE_URL},
        {"category": "international_eligibility", "requirement": "International students", "status": "met", "evidence": "scholarships to international students", "source_url": OFFICIAL_PAGE_URL},
        {"category": "academic_requirements", "requirement": "Minimum GPA", "status": "met", "evidence": "Minimum CGPA 7.0 on a 10 point scale.", "source_url": OFFICIAL_PAGE_URL},
        {"category": "language_requirements", "requirement": "IELTS", "status": "unknown", "evidence": "Applicants must have IELTS 6.5.", "source_url": OFFICIAL_PAGE_URL},
        {"category": "field_of_study", "requirement": "Field", "status": "met", "evidence": "degree in Computer Science at Test University", "source_url": OFFICIAL_PAGE_URL},
        {"category": "funding", "requirement": "Funding", "status": "met", "evidence": "Awards provide full tuition.", "source_url": OFFICIAL_PAGE_URL},
        {"category": "deadline", "requirement": "Deadline", "required_value": "30 June 2027", "status": "met", "evidence": "The application deadline is 30 June 2027.", "source_url": OFFICIAL_PAGE_URL},
    ],
    "missing_documents": [],
    "missing_info": [],
    "disqualifying_factors": [],
    "notes": "Official source quotes support award details; language score is missing.",
}


class TestVerifierAgent:
    def test_official_source_must_match_provider_or_institution(self):
        assert _is_official_source("https://test.edu/scholarship", SAMPLE_OPPORTUNITY)
        assert not _is_official_source("https://scholarship-blog.example/scholarship", SAMPLE_OPPORTUNITY)

    def test_deadline_requires_a_specific_date_copied_from_official_quote(self):
        assert _deadline_value_is_supported(
            "The application deadline is 30 June 2027.", "30 June 2027"
        )
        assert not _deadline_value_is_supported(
            "Application deadlines are updated annually in the second quarter.",
            "Specific deadline date",
        )
        assert not _deadline_value_is_supported(
            "This programme has no deadline listed.", "Specific deadline date"
        )

    def test_deadline_currentness_handles_exact_expired_and_missing_values(self):
        from datetime import date, timedelta

        today = date(2026, 10, 20)
        assert deadline_is_current("2026-10-21", today=today) is True
        assert deadline_is_current("2026-10-19", today=today) is False
        assert deadline_is_current(None, today=today) is None
        assert deadline_is_current("deadlines updated annually", today=today) is None

    @pytest.mark.asyncio
    async def test_verified_requires_cited_first_party_source(self):
        response = dict(MOCK_ELIGIBLE_ASSESSMENT)
        state = GraphState(
            run_id="test-run", student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE, enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[SAMPLE_OPPORTUNITY.model_copy(deep=True)],
        )
        with patch("app.agents.verifier.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.verifier.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.agents.verifier._fetch_official_text", new_callable=AsyncMock, return_value=(OFFICIAL_PAGE_URL, OFFICIAL_PAGE_TEXT)):
            mock_search.return_value = [{
                "title": "Test Graduate Scholarship eligibility",
                "url": "https://test.edu/scholarship",
                "content": "Search result snippet",
            }]
            import json
            mock_llm.return_value = json.dumps(response)
            result = await run_verifier(state)
        assessment = result.eligibility_assessments[0]
        assert assessment.source_verified is True
        assert assessment.status == EligibilityStatus.POTENTIALLY_ELIGIBLE
        assert result.discovered_opportunities[0].official_source_status.value == "verified"
        assert result.discovered_opportunities[0].requirements_status.value == "verified"
        assert result.discovered_opportunities[0].deadline_status.value == "verified"
        assert all(check.evidence in OFFICIAL_PAGE_TEXT for check in assessment.requirement_checks if check.evidence)

    @pytest.mark.asyncio
    async def test_generic_deadline_text_stays_explicitly_unknown(self):
        import json

        response = {**MOCK_ELIGIBLE_ASSESSMENT}
        response["requirement_checks"] = [dict(check) for check in MOCK_ELIGIBLE_ASSESSMENT["requirement_checks"]]
        deadline = next(item for item in response["requirement_checks"] if item["category"] == "deadline")
        deadline.update({
            "required_value": "Specific deadline date",
            "evidence": "Application deadlines are updated annually in the second quarter.",
        })
        page_text = OFFICIAL_PAGE_TEXT + " Application deadlines are updated annually in the second quarter."
        state = GraphState(
            run_id="test-run", student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE, enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[SAMPLE_OPPORTUNITY.model_copy(deep=True)],
        )
        with patch("app.agents.verifier.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.verifier.call_llm", new_callable=AsyncMock, return_value=json.dumps(response)), \
             patch("app.agents.verifier._fetch_official_text", new_callable=AsyncMock, return_value=(OFFICIAL_PAGE_URL, page_text)):
            mock_search.return_value = [{"title": "Test award", "url": OFFICIAL_PAGE_URL}]
            result = await run_verifier(state)
        opportunity = result.discovered_opportunities[0]
        assessment = result.eligibility_assessments[0]
        deadline_check = next(c for c in assessment.requirement_checks if c.category == "deadline")
        assert deadline_check.status == "unknown"
        assert deadline_check.required_value is None
        assert opportunity.application_deadline is None
        assert opportunity.deadline_status.value == "unknown"

    @pytest.mark.asyncio
    async def test_verifier_assesses_opportunities(self):
        """Verifier should produce assessments for all discovered opportunities."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[SAMPLE_OPPORTUNITY],
        )
        with patch("app.agents.verifier.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.verifier.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_search.return_value = []
            import json
            mock_llm.return_value = json.dumps(MOCK_ELIGIBLE_ASSESSMENT)

            result = await run_verifier(state)

        assert len(result.eligibility_assessments) == 1
        assert result.eligibility_assessments[0].scholarship_id == SAMPLE_OPPORTUNITY.id
        assert "eligibility_verifier" in result.completed_agents

    @pytest.mark.asyncio
    async def test_verifier_identifies_missing_language_scores(self):
        """Verifier must flag missing IELTS/TOEFL as a gap for Rahul."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[SAMPLE_OPPORTUNITY],
        )
        with patch("app.agents.verifier.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.verifier.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_search.return_value = []
            import json
            mock_llm.return_value = json.dumps(MOCK_ELIGIBLE_ASSESSMENT)

            result = await run_verifier(state)

        assessment = result.eligibility_assessments[0]
        # IELTS should appear in missing documents
        missing_text = " ".join(assessment.missing_documents + assessment.missing_info).lower()
        assert "ielts" in missing_text or "english" in missing_text or "language" in missing_text

    @pytest.mark.asyncio
    async def test_verifier_handles_empty_opportunities(self):
        """Verifier should skip gracefully if no opportunities to verify."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[],
        )
        result = await run_verifier(state)
        assert result.eligibility_assessments == []
        assert "eligibility_verifier" in result.completed_agents

    @pytest.mark.asyncio
    async def test_verifier_continues_on_single_failure(self):
        """If one opportunity fails verification, others should still be processed."""
        opp2 = ScholarshipOpportunity(
            id="test-opp-2",
            name="Second Scholarship",
            provider="Another Uni",
            country="Germany",
        )
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[SAMPLE_OPPORTUNITY, opp2],
        )
        import json

        call_count = 0

        async def mock_llm_with_failure(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated LLM failure")
            return json.dumps(MOCK_ELIGIBLE_ASSESSMENT)

        with patch("app.agents.verifier.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.verifier.call_llm", side_effect=mock_llm_with_failure):
            mock_search.return_value = []
            result = await run_verifier(state)

        # Both opportunities should have assessments (one failed = needs_verification)
        assert len(result.eligibility_assessments) == 2
        assert result.eligibility_assessments[0].status == EligibilityStatus.NEEDS_VERIFICATION

    @pytest.mark.asyncio
    async def test_verifier_never_marks_unknown_requirement_as_met(self):
        """If a requirement is not in the sources, it must be unknown, not met."""
        ineligible_assessment = {
            "status": "ineligible",
            "confidence": 0.9,
            "requirement_checks": [
                {
                    "requirement": "GPA Minimum 8.5",
                    "student_value": "8.2/10",
                    "required_value": "8.5/10",
                    "status": "not_met",
                    "evidence": "Student CGPA 8.2 is below required 8.5"
                }
            ],
            "missing_documents": [],
            "missing_info": [],
            "disqualifying_factors": ["GPA below threshold"],
            "notes": "Student does not meet minimum GPA requirement",
            "source_verified": True,
        }
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[SAMPLE_OPPORTUNITY],
        )
        with patch("app.agents.verifier.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.verifier.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_search.return_value = []
            import json
            mock_llm.return_value = json.dumps(ineligible_assessment)

            result = await run_verifier(state)

        assessment = result.eligibility_assessments[0]
        assert assessment.status == EligibilityStatus.NEEDS_VERIFICATION
        assert assessment.disqualifying_factors == []
        assert assessment.requirement_checks == []
        assert assessment.source_verified is False
