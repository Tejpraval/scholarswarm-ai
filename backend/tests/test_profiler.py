"""Tests for the Student Profiler agent."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.state import GraphState
from app.agents.profiler import run_profiler, _compute_completeness
from app.models.student import StudentProfile, AcademicProfile, DegreeLevel, DEMO_PROFILE
from app.models.workflow import AgentStatus


@pytest.fixture
def demo_state():
    return GraphState(
        run_id="test-run-1",
        student_id=DEMO_PROFILE.id,
        student_profile=DEMO_PROFILE,
    )


@pytest.fixture
def incomplete_state():
    profile = StudentProfile(name="Incomplete Student")
    return GraphState(
        run_id="test-run-2",
        student_id=profile.id,
        student_profile=profile,
    )


class TestComputeCompleteness:
    def test_complete_profile_has_high_score(self):
        completeness, missing = _compute_completeness(DEMO_PROFILE)
        assert completeness > 0.6
        # Demo profile is missing language scores
        assert "language_scores" in missing

    def test_empty_profile_has_low_score(self):
        p = StudentProfile(name="Empty")
        completeness, missing = _compute_completeness(p)
        assert completeness < 0.3
        assert len(missing) > 5

    def test_missing_fields_list_is_accurate(self):
        p = StudentProfile(
            name="Partial",
            academic=AcademicProfile(cgpa=8.5, cgpa_scale=10.0),
        )
        completeness, missing = _compute_completeness(p)
        assert "institution" in missing
        assert "graduation_year" in missing
        assert "cgpa" not in missing  # cgpa is provided


class TestProfilerAgent:
    @pytest.mark.asyncio
    async def test_profiler_runs_on_demo_profile(self):
        """Profiler should complete successfully on the demo profile."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
        )
        with patch("app.agents.profiler._fetch_github_profile", new_callable=AsyncMock) as mock_gh, \
             patch("app.agents.profiler._extract_profile_from_documents", new_callable=AsyncMock) as mock_docs:
            mock_gh.return_value = {
                "username": "rahul-example",
                "public_repos": 5,
                "top_languages": ["Python", "JavaScript"],
                "repos_summary": [],
            }
            mock_docs.return_value = {}

            result = await run_profiler(state)

        assert result.profile_validated is True
        assert result.enriched_profile is not None
        assert "student_profiler" in result.completed_agents
        # Check events were emitted
        statuses = [ev.status for ev in result.events]
        assert AgentStatus.COMPLETED in statuses

    @pytest.mark.asyncio
    async def test_profiler_handles_missing_profile(self):
        """Profiler should fail gracefully when no profile is provided."""
        state = GraphState(
            run_id="test-run",
            student_id="none",
        )
        result = await run_profiler(state)
        assert result.workflow_error is not None
        assert any(ev.status == AgentStatus.FAILED for ev in result.events)

    @pytest.mark.asyncio
    async def test_profiler_handles_github_failure(self):
        """Profiler should continue if GitHub fetch fails."""
        state = GraphState(
            run_id="test-run",
            student_id=DEMO_PROFILE.id,
            student_profile=DEMO_PROFILE,
        )
        with patch("app.agents.profiler._fetch_github_profile", new_callable=AsyncMock) as mock_gh, \
             patch("app.agents.profiler._extract_profile_from_documents", new_callable=AsyncMock) as mock_docs:
            mock_gh.return_value = None  # GitHub unavailable
            mock_docs.return_value = {}

            result = await run_profiler(state)

        assert result.profile_validated is True
        assert result.github_data is None
        assert "student_profiler" in result.completed_agents

    @pytest.mark.asyncio
    async def test_profiler_works_on_different_student(self):
        """Profiler must work on a completely different student without code changes."""
        different_student = StudentProfile(
            name="Ananya Kumar",
            nationality="Indian",
            academic=AcademicProfile(
                degree_level=DegreeLevel.BACHELORS,
                degree_name="B.E. Electronics",
                institution="Anna University",
                cgpa=7.8,
                cgpa_scale=10.0,
                graduation_year=2025,
            ),
            skills=["C++", "Embedded Systems", "VLSI"],
            destination_preferences=["Japan", "South Korea"],
        )
        state = GraphState(
            run_id="test-run-different",
            student_id=different_student.id,
            student_profile=different_student,
        )
        with patch("app.agents.profiler._fetch_github_profile", new_callable=AsyncMock) as mock_gh, \
             patch("app.agents.profiler._extract_profile_from_documents", new_callable=AsyncMock) as mock_docs:
            mock_gh.return_value = None
            mock_docs.return_value = {}

            result = await run_profiler(state)

        assert result.profile_validated is True
        assert result.enriched_profile.name == "Ananya Kumar"
