"""Tests for the Matching and Application Agent."""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from app.agents.state import GraphState
from app.agents.matcher import run_matcher, _score_opportunity, _is_recommendable
from app.models.student import DEMO_PROFILE, StudentProfile, AcademicProfile, DegreeLevel, FundingPreference
from app.models.scholarship import (
    ScholarshipOpportunity, EligibilityAssessment, MatchResult,
    EligibilityStatus, FundingType, SourceType, VerificationStatus, RequirementCheck, EvidenceStage
)
from app.models.workflow import AgentStatus


def make_opp(name, country, funding=FundingType.FULL, cgpa=None, fields=None):
    return ScholarshipOpportunity(
        name=name,
        provider=f"{name} Provider",
        country=country,
        degree_levels=["masters"],
        fields_of_study=fields or ["Computer Science"],
        funding_type=funding,
        verification_status=VerificationStatus.VERIFIED,
        official_url=f"https://example.com/{name.lower().replace(' ', '-')}",
        official_source_status=EvidenceStage.VERIFIED,
        requirements_status=EvidenceStage.VERIFIED,
        deadline_status=EvidenceStage.UNKNOWN,
        min_cgpa=cgpa,
        source_url=f"https://example.com/{name.lower().replace(' ', '-')}",
    )


def make_assessment(opp_id, status, confidence):
    return EligibilityAssessment(
        scholarship_id=opp_id,
        student_id=DEMO_PROFILE.id,
        status=status,
        confidence=confidence,
    )


def make_confirmed_assessment(opp, status=EligibilityStatus.ELIGIBLE):
    assessment = make_assessment(opp.id, status, 0.9)
    categories = [
        "opportunity_exists", "degree_level", "international_eligibility",
        "academic_requirements", "language_requirements", "field_of_study", "funding",
    ]
    assessment.requirement_checks = [RequirementCheck(
        category=category, requirement=category, status="met",
        evidence=f"Official source evidence confirms {category.replace('_', ' ')} requirement.",
        source_url=opp.official_url,
    ) for category in categories]
    return assessment


class TestScoringModel:
    def test_full_funding_preferred_destination_scores_high(self):
        opp = make_opp("Full Fund Canada", "Canada", FundingType.FULL)
        assessment = make_assessment(opp.id, EligibilityStatus.ELIGIBLE, 0.9)
        score, breakdown = _score_opportunity(opp, assessment, DEMO_PROFILE)
        assert score > 60  # Should score well
        assert breakdown["funding_match"] > 0
        assert breakdown["destination_preference"] > 0

    def test_ineligible_opportunity_scores_lower(self):
        opp = make_opp("High Bar Scholarship", "Germany", FundingType.FULL, cgpa=9.5)
        eligible_opp = make_opp("Regular Scholarship", "Canada", FundingType.FULL, cgpa=7.0)

        ineligible_assessment = make_assessment(opp.id, EligibilityStatus.INELIGIBLE, 0.95)
        eligible_assessment = make_assessment(eligible_opp.id, EligibilityStatus.ELIGIBLE, 0.85)

        ineligible_score, _ = _score_opportunity(opp, ineligible_assessment, DEMO_PROFILE)
        eligible_score, _ = _score_opportunity(eligible_opp, eligible_assessment, DEMO_PROFILE)

        assert eligible_score > ineligible_score

    def test_match_score_max_100(self):
        opp = make_opp("Perfect Match", "Canada", FundingType.FULL,
                       fields=["Artificial Intelligence", "Machine Learning"])
        assessment = make_assessment(opp.id, EligibilityStatus.ELIGIBLE, 1.0)
        score, _ = _score_opportunity(opp, assessment, DEMO_PROFILE)
        assert score <= 100.0

    def test_match_score_min_0(self):
        opp = make_opp("Bad Match", "Iceland", FundingType.UNKNOWN)
        assessment = make_assessment(opp.id, EligibilityStatus.INELIGIBLE, 0.0)
        score, _ = _score_opportunity(opp, assessment, DEMO_PROFILE)
        assert score >= 0.0

    def test_eligibility_and_score_are_separate(self):
        """A high score must not imply confirmed eligibility."""
        opp = make_opp("Unverified Scholarship", "Singapore", FundingType.FULL)
        # Potentially eligible with high funding match — score could be decent
        assessment = make_assessment(opp.id, EligibilityStatus.NEEDS_VERIFICATION, 0.5)
        score, breakdown = _score_opportunity(opp, assessment, DEMO_PROFILE)
        # Score reflects uncertainty — eligibility_confidence should not be 30 (max)
        assert breakdown["eligibility_confidence"] < 30.0

    def test_cgpa_fit_penalizes_unmet_requirement(self):
        # Student CGPA 8.2/10 = 82%. Requirement 9.5/10 = 95% (clear fail)
        opp = make_opp("High CGPA Req", "Germany", cgpa=9.5)
        assessment = make_assessment(opp.id, EligibilityStatus.INELIGIBLE, 0.9)
        score, breakdown = _score_opportunity(opp, assessment, DEMO_PROFILE)
        # 8.2/10 = 82%, required 9.5/10 = 95% — student falls well below
        assert breakdown["cgpa_fit"] == 0.0


class TestMatcherAgent:
    def test_expired_verified_deadline_is_never_recommendable(self):
        opportunity = make_opp("Expired Award", "Canada", FundingType.FULL)
        opportunity.deadline_status = EvidenceStage.VERIFIED
        opportunity.application_deadline = (date.today() - timedelta(days=1)).isoformat()
        assessment = make_confirmed_assessment(opportunity)
        match = MatchResult(
            scholarship_id=opportunity.id,
            student_id=DEMO_PROFILE.id,
            rank=1,
            match_score=99,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            eligibility_confidence=assessment.confidence,
            scholarship=opportunity,
            eligibility=assessment,
        )
        assert not _is_recommendable(match, DEMO_PROFILE)

    @pytest.mark.asyncio
    async def test_matcher_returns_top_5(self):
        """Matcher should return at most 5 top matches."""
        opps = [make_opp(f"Scholarship {i}", "Canada", FundingType.FULL) for i in range(8)]
        assessments = [make_confirmed_assessment(o) for o in opps]
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=opps,
            eligibility_assessments=assessments,
        )
        with patch("app.agents.matcher.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.agents.matcher._generate_sop", new_callable=AsyncMock) as mock_sop:
            mock_llm.return_value = "This scholarship is recommended because it offers full funding for AI/ML."
            from app.models.application import ApplicationDraft
            mock_sop.return_value = ApplicationDraft(
                run_id="test-run",
                student_id=DEMO_PROFILE.id,
                scholarship_id=opps[0].id,
                scholarship_name=opps[0].name,
                draft_text="Draft SOP text",
                placeholders=["IELTS_SCORE"],
            )
            result = await run_matcher(state)

        assert len(result.top_matches) == 5
        assert len(result.match_results) == 8  # All ranked

    @pytest.mark.asyncio
    async def test_top_matches_never_exceed_verified_suitable_opportunities(self):
        from app.models.scholarship import VerificationStatus
        opps = [make_opp(f"Scholarship {i}", "Canada") for i in range(6)]
        for opp in opps[1:]:
            opp.verification_status = VerificationStatus.PARTIAL
        assessments = [make_confirmed_assessment(opps[0])] + [
            make_assessment(o.id, EligibilityStatus.POTENTIALLY_ELIGIBLE, 0.7) for o in opps[1:]
        ]
        state = GraphState(
            run_id="test-run", student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE, enriched_profile=DEMO_PROFILE,
            discovered_opportunities=opps, eligibility_assessments=assessments,
        )
        with patch("app.agents.matcher.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.agents.matcher._generate_sop", new_callable=AsyncMock) as mock_sop:
            mock_llm.return_value = "A factual, short explanation."
            result = await run_matcher(state)
        assert len(result.match_results) == 6
        assert len(result.top_matches) == 1
        assert result.top_matches[0].scholarship.verification_status == VerificationStatus.VERIFIED
        mock_sop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_top_matches_exclude_confirmed_unmet_requirements(self):
        opp = make_opp("Timing Conflict Award", "Canada")
        assessment = make_assessment(opp.id, EligibilityStatus.POTENTIALLY_ELIGIBLE, 0.7)
        assessment.requirement_checks = [RequirementCheck(
            requirement="Graduation year", student_value="2025",
            required_value="2027 or later", status="not_met",
        )]
        state = GraphState(
            run_id="test-run", student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE, enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[opp], eligibility_assessments=[assessment],
        )
        with patch("app.agents.matcher.call_llm", new_callable=AsyncMock):
            result = await run_matcher(state)
        assert len(result.match_results) == 1
        assert result.top_matches == []
        assert result.sop_draft is None

    def test_recommendations_respect_destination_and_known_uncertainty(self):
        from app.agents.matcher import _is_recommendable
        profile = StudentProfile(
            name="Destination Student",
            academic=AcademicProfile(degree_name="Environmental Science"),
            destination_preferences=["Australia", "Japan"],
        )
        japan = make_opp("Japan Award", "Japan")
        assessment = make_confirmed_assessment(japan)
        result = MatchResult(
            scholarship_id=japan.id, student_id=profile.id, rank=1,
            match_score=80, eligibility_status=assessment.status,
            eligibility_confidence=assessment.confidence,
            scholarship=japan, eligibility=assessment,
        )
        assert _is_recommendable(result, profile)

        germany = make_opp("Germany Award", "Germany")
        result.scholarship = germany
        result.scholarship_id = germany.id
        assert not _is_recommendable(result, profile)

        result.scholarship = japan
        result.scholarship_id = japan.id
        result.eligibility_status = EligibilityStatus.NEEDS_VERIFICATION
        assert not _is_recommendable(result, profile)

    @pytest.mark.asyncio
    async def test_matcher_ranks_by_score(self):
        """Results should be sorted descending by score."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
            discovered_opportunities=[
                make_opp("Full Fund Canada", "Canada", FundingType.FULL,
                         fields=["Artificial Intelligence"]),
                make_opp("No Fund Unrelated", "Iceland", FundingType.UNKNOWN),
            ],
            eligibility_assessments=[
                make_assessment("", EligibilityStatus.ELIGIBLE, 0.9),
                make_assessment("", EligibilityStatus.INELIGIBLE, 0.1),
            ],
        )
        # Fix assessment IDs
        opps = state.discovered_opportunities
        assessments = [
            make_assessment(opps[0].id, EligibilityStatus.ELIGIBLE, 0.9),
            make_assessment(opps[1].id, EligibilityStatus.INELIGIBLE, 0.1),
        ]
        state.eligibility_assessments = assessments

        with patch("app.agents.matcher.call_llm", new_callable=AsyncMock) as mock_llm, \
             patch("app.agents.matcher._generate_sop", new_callable=AsyncMock) as mock_sop:
            mock_llm.return_value = "Recommended for strong AI/ML alignment."
            from app.models.application import ApplicationDraft
            mock_sop.return_value = ApplicationDraft(
                run_id="test-run",
                student_id=DEMO_PROFILE.id,
                scholarship_id=opps[0].id,
                scholarship_name=opps[0].name,
                draft_text="Draft",
                placeholders=[],
            )
            result = await run_matcher(state)

        scores = [m.match_score for m in result.match_results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_sop_does_not_use_fabricated_achievements(self):
        """SOP should only use facts from the profile, not invented ones."""
        from app.agents.matcher import _generate_sop
        minimal_profile = StudentProfile(
            name="Min Student",
            academic=AcademicProfile(
                degree_name="B.Tech CS",
                cgpa=7.5,
                institution="Test University",
            ),
            skills=["Python"],
        )
        opp = make_opp("Test Scholarship", "Canada")

        sop_response = """Dear Admissions Committee,

I am Min Student, a B.Tech CS student at Test University with a CGPA of 7.5/10.0.
My skill in Python has prepared me for this opportunity.
[IELTS_SCORE] is required but I haven't taken the test yet.
[FULL_WORK_EXPERIENCE] is not currently available.

--- DRAFT ONLY — Review all [PLACEHOLDER] tokens before submission ---"""

        with patch("app.agents.matcher.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = sop_response
            draft = await _generate_sop(opp, minimal_profile, "test-run")

        # Verify draft is marked as draft
        assert draft.is_draft is True
        # Verify only real facts were noted as used
        facts_text = " ".join(draft.facts_used)
        assert "Min Student" in facts_text
        assert "7.5" in facts_text
        # Should not claim publications or awards not in profile
        assert "published" not in draft.draft_text.lower() or "placeholder" in draft.draft_text.lower()
        assert "first-generation" not in draft.draft_text.lower()
        mock_llm.assert_not_awaited()
