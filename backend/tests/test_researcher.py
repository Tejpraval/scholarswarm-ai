"""Tests for the Scholarship Researcher agent."""
import pytest
import json
from unittest.mock import AsyncMock, patch

from app.agents.state import GraphState
from app.agents.researcher import (
    run_researcher, _deduplicate, _stable_id, _build_search_queries,
    _parse_opportunities_from_search, InvalidResearchOutput,
)
from app.models.student import DEMO_PROFILE, StudentProfile, AcademicProfile, DegreeLevel
from app.models.scholarship import ScholarshipOpportunity, SourceType, FundingType
from app.models.workflow import AgentStatus


MOCK_SEARCH_RESULTS = [
    {
        "title": "DAAD Scholarship Germany",
        "url": "https://www.daad.de/en/study-and-research-in-germany/scholarships/",
        "content": "DAAD offers fully funded scholarships for international students to pursue masters degrees in Germany. Open to students from developing countries including India. Deadline: typically November-December.",
    }
]

MOCK_PARSED_OPPORTUNITY = [
    {
        "name": "DAAD Scholarship",
        "provider": "DAAD",
        "country": "Germany",
        "university": None,
        "source_type": "government",
        "degree_levels": ["masters", "phd"],
        "fields_of_study": ["Computer Science", "Engineering"],
        "funding_type": "full_funding",
        "funding_description": "Full funding including tuition and living allowance",
        "funding_amount_usd": None,
        "covers_tuition": True,
        "covers_living": True,
        "min_cgpa": None,
        "required_language_tests": ["IELTS", "German language (B2)"],
        "citizenship_restrictions": [],
        "open_to_indian_nationals": True,
        "application_deadline": "2025-11-30",
        "official_url": "https://www.daad.de/en/",
        "source_url": "https://www.daad.de/en/study-and-research-in-germany/scholarships/",
        "source_snippet": "DAAD offers fully funded scholarships for international students",
        "application_instructions": "Apply via DAAD portal",
        "required_documents": ["CV", "Motivation letter", "Transcripts"],
    }
]


class TestDeduplication:
    def test_exact_duplicates_removed(self):
        opp1 = ScholarshipOpportunity(
            id=_stable_id("DAAD", "DAAD", "Germany"),
            name="DAAD Scholarship",
            provider="DAAD",
            country="Germany",
        )
        opp2 = ScholarshipOpportunity(
            id=_stable_id("DAAD", "DAAD", "Germany"),
            name="DAAD Scholarship",
            provider="DAAD",
            country="Germany",
        )
        result = _deduplicate([opp1, opp2])
        assert len(result) == 1

    def test_different_scholarships_not_deduplicated(self):
        opp1 = ScholarshipOpportunity(
            id=_stable_id("DAAD", "DAAD", "Germany"),
            name="DAAD Scholarship",
            provider="DAAD",
            country="Germany",
        )
        opp2 = ScholarshipOpportunity(
            id=_stable_id("NTU Scholarship", "NTU", "Singapore"),
            name="NTU Scholarship",
            provider="NTU",
            country="Singapore",
        )
        result = _deduplicate([opp1, opp2])
        assert len(result) == 2

    def test_same_program_with_acronym_and_full_name_is_deduplicated(self):
        first = ScholarshipOpportunity(
            name="DAAD Zuse School of Excellence in Learning and Intelligent Systems (ELIZA)",
            provider="DAAD", country="Germany", source_snippet="ELIZA scholarship",
        )
        second = ScholarshipOpportunity(
            name="Konrad Zuse School ELIZA", provider="DAAD", country="Germany",
            source_snippet="More complete official ELIZA scholarship entry",
            application_deadline="2026-09-30",
        )
        result = _deduplicate([first, second])
        assert len(result) == 1
        assert result[0].application_deadline == "2026-09-30"

    def test_same_award_title_is_deduplicated_when_searches_name_different_providers(self):
        first = ScholarshipOpportunity(
            name="Vector in AI", provider="Ontario universities", country="Canada",
        )
        second = ScholarshipOpportunity(
            name="Vector in AI", provider="Vector Institute / Ontario universities", country="Canada",
            official_url="https://vectorinstitute.ai/scholarships",
        )
        result = _deduplicate([first, second])
        assert len(result) == 1
        assert result[0].official_url == "https://vectorinstitute.ai/scholarships"


class TestSearchQueryGeneration:
    def test_queries_cover_all_destinations(self):
        queries = _build_search_queries(DEMO_PROFILE)
        query_text = " ".join(queries).lower()
        assert "canada" in query_text
        assert "germany" in query_text
        assert "singapore" in query_text

    def test_queries_include_field(self):
        queries = _build_search_queries(DEMO_PROFILE)
        query_text = " ".join(queries).lower()
        # Should contain AI/ML related terms
        assert any(term in query_text for term in ["ai", "machine learning", "computer science"])

    def test_queries_adapt_destinations_nationality_and_degree(self):
        profile = DEMO_PROFILE.model_copy(deep=True)
        profile.nationality = "Malaysian"
        profile.destination_preferences = ["Australia", "Japan"]
        profile.target_degree = DegreeLevel.PHD

        query_text = " ".join(_build_search_queries(profile)).casefold()
        assert "australia" in query_text
        assert "japan" in query_text
        assert "malaysian" in query_text
        assert "phd" in query_text
        assert "india" not in query_text
        assert "daad" not in query_text
        assert "canada" not in query_text
        assert "singapore" not in query_text


class TestResearcherAgent:
    @pytest.mark.asyncio
    async def test_invalid_json_is_reported_as_structured_output_failure(self):
        with patch("app.agents.researcher.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "this is not JSON"
            with pytest.raises(InvalidResearchOutput):
                await _parse_opportunities_from_search(
                    "scholarships", MOCK_SEARCH_RESULTS, DEMO_PROFILE
                )
        assert mock_llm.await_count == 3

    @pytest.mark.asyncio
    async def test_invalid_json_is_retried_once_and_valid_output_is_preserved(self):
        with patch("app.agents.researcher.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                "not JSON",
                json.dumps({"opportunities": MOCK_PARSED_OPPORTUNITY}),
            ]
            opportunities = await _parse_opportunities_from_search(
                "scholarships", MOCK_SEARCH_RESULTS, DEMO_PROFILE
            )
        assert len(opportunities) == 1
        assert opportunities[0].name == "DAAD Scholarship"
        assert mock_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_schema_failure_is_retried_and_unlinked_source_is_rejected(self):
        valid = dict(MOCK_PARSED_OPPORTUNITY[0])
        valid["source_url"] = MOCK_SEARCH_RESULTS[0]["url"]
        with patch("app.agents.researcher.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                json.dumps({"opportunities": [{"name": "Missing provider"}]}),
                json.dumps({"opportunities": [valid]}),
            ]
            opportunities = await _parse_opportunities_from_search(
                "scholarships", MOCK_SEARCH_RESULTS, DEMO_PROFILE
            )
        assert [item.name for item in opportunities] == ["DAAD Scholarship"]
        assert opportunities[0].official_url is None
        assert mock_llm.await_count == 2

    @pytest.mark.asyncio
    async def test_second_bounded_structured_retry_can_recover_malformed_output(self):
        valid = dict(MOCK_PARSED_OPPORTUNITY[0])
        valid["source_url"] = MOCK_SEARCH_RESULTS[0]["url"]
        with patch("app.agents.researcher.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                "not JSON",
                "still not JSON",
                json.dumps({"opportunities": [valid]}),
            ]
            opportunities = await _parse_opportunities_from_search(
                "scholarships", MOCK_SEARCH_RESULTS, DEMO_PROFILE
            )
        assert [item.name for item in opportunities] == ["DAAD Scholarship"]
        assert mock_llm.await_count == 3

    @pytest.mark.asyncio
    async def test_provider_exception_is_not_silently_converted_to_empty_results(self):
        with patch("app.agents.researcher.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("provider unavailable")
            with pytest.raises(RuntimeError, match="provider unavailable"):
                await _parse_opportunities_from_search(
                    "scholarships", MOCK_SEARCH_RESULTS, DEMO_PROFILE
                )

    @pytest.mark.asyncio
    async def test_llm_rate_limit_keeps_results_from_other_queries(self):
        profile = DEMO_PROFILE
        opportunity = ScholarshipOpportunity(
            name="Partial Result", provider="Provider", country="Canada",
            source_url="https://provider.example/scholarship",
        )
        state = GraphState(
            run_id="test-run", student_id=profile.id,
            student_profile=profile, enriched_profile=profile,
        )
        with patch("app.agents.researcher._build_search_queries", return_value=["q1", "q2"]), \
             patch("app.agents.researcher.search_web", new_callable=AsyncMock, return_value=MOCK_SEARCH_RESULTS), \
             patch("app.agents.researcher._parse_opportunities_from_search", new_callable=AsyncMock) as mock_parse:
            mock_parse.side_effect = [RuntimeError("429 rate limit"), [opportunity]]
            result = await run_researcher(state)
        assert len(result.discovered_opportunities) == 1
        assert "research model call" in result.research_error
        assert any("unavailable" in event.message for event in result.events)

    @pytest.mark.asyncio
    async def test_failed_search_query_keeps_prior_results(self):
        opportunity = ScholarshipOpportunity(
            name="Partial Result", provider="Provider", country="Canada",
            source_url="https://provider.example/scholarship",
        )
        state = GraphState(
            run_id="test-run", student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE, enriched_profile=DEMO_PROFILE,
        )
        with patch("app.agents.researcher._build_search_queries", return_value=["q1", "q2"]), \
             patch("app.agents.researcher.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.researcher._parse_opportunities_from_search", new_callable=AsyncMock, return_value=[opportunity]):
            mock_search.side_effect = [MOCK_SEARCH_RESULTS, RuntimeError("timeout")]
            result = await run_researcher(state)
        assert len(result.discovered_opportunities) == 1
        assert "search query" in result.research_error

    @pytest.mark.asyncio
    async def test_researcher_discovers_opportunities(self):
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
        )
        with patch("app.agents.researcher.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.researcher._parse_opportunities_from_search", new_callable=AsyncMock) as mock_parse:
            mock_search.return_value = MOCK_SEARCH_RESULTS
            mock_parse.return_value = [
                ScholarshipOpportunity(
                    id=_stable_id("DAAD Scholarship", "DAAD", "Germany"),
                    name="DAAD Scholarship",
                    provider="DAAD",
                    country="Germany",
                    funding_type=FundingType.FULL,
                    source_url="https://daad.de",
                )
            ]
            result = await run_researcher(state)

        assert len(result.discovered_opportunities) >= 1
        assert "scholarship_researcher" in result.completed_agents

    @pytest.mark.asyncio
    async def test_researcher_handles_search_failure(self):
        """Researcher should handle partial search failures gracefully."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
        )
        with patch("app.agents.researcher.search_web", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = RuntimeError("Search API unavailable")
            result = await run_researcher(state)

        # Should not crash — research_error is set
        assert result.research_error is not None
        assert any(ev.status == AgentStatus.RETRYING for ev in result.events)

    @pytest.mark.asyncio
    async def test_researcher_never_fabricates_results(self):
        """When search returns nothing, researcher should return empty list, not fabricated data."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
            enriched_profile=DEMO_PROFILE,
        )
        with patch("app.agents.researcher.search_web", new_callable=AsyncMock) as mock_search, \
             patch("app.agents.researcher._parse_opportunities_from_search", new_callable=AsyncMock) as mock_parse:
            mock_search.return_value = []
            mock_parse.return_value = []
            result = await run_researcher(state)

        # Zero results is acceptable — we do not fabricate
        assert isinstance(result.discovered_opportunities, list)
