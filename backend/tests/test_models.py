"""Tests for data models and validation."""
import pytest
from pydantic import ValidationError

from app.models.student import StudentProfile, AcademicProfile, DegreeLevel, FundingPreference, DEMO_PROFILE
from app.models.scholarship import (
    ScholarshipOpportunity, EligibilityAssessment, MatchResult,
    EligibilityStatus, SourceType, FundingType
)
from app.models.workflow import AgentEvent, AgentStatus, WorkflowRun, RunStatus
from app.models.application import ApplicationDraft


class TestStudentProfile:
    def test_demo_profile_is_valid(self):
        """The pre-built demo profile should always be valid."""
        assert DEMO_PROFILE.name == "Rahul Sharma"
        assert DEMO_PROFILE.academic.cgpa == 8.2
        assert len(DEMO_PROFILE.destination_preferences) == 3
        assert DEMO_PROFILE.target_degree == DegreeLevel.MASTERS

    def test_minimal_profile_creation(self):
        """Can create profile with just a name."""
        p = StudentProfile(name="Test User")
        assert p.name == "Test User"
        assert p.id is not None
        assert p.skills == []

    def test_cgpa_validation(self):
        """CGPA must be within 0–10."""
        with pytest.raises(ValidationError):
            AcademicProfile(cgpa=11.0, cgpa_scale=10.0)

    def test_graduation_year_validation(self):
        """Graduation year must be reasonable."""
        with pytest.raises(ValidationError):
            AcademicProfile(graduation_year=1850)

    def test_different_student_profile(self):
        """A completely different student profile should work without any code changes."""
        priya = StudentProfile(
            name="Priya Patel",
            nationality="Indian",
            academic=AcademicProfile(
                degree_level=DegreeLevel.MASTERS,
                degree_name="M.Sc Data Science",
                institution="IIT Bombay",
                cgpa=9.1,
                cgpa_scale=10.0,
                graduation_year=2024,
            ),
            skills=["Python", "R", "Statistics", "ML"],
            destination_preferences=["USA", "UK", "Australia"],
            target_degree=DegreeLevel.PHD,
            target_field="Data Science",
            funding_preference=FundingPreference.FULL,
        )
        assert priya.name == "Priya Patel"
        assert priya.academic.cgpa == 9.1
        assert "USA" in priya.destination_preferences

    def test_profile_completeness_missing_fields(self):
        """Profile with missing fields should have low completeness."""
        p = StudentProfile(name="Incomplete User")
        # Profile has name but nothing else
        assert p.profile_completeness == 0.0
        assert len(p.missing_fields) == 0  # Not computed until profiler runs


class TestScholarshipModels:
    def test_scholarship_creation(self):
        opp = ScholarshipOpportunity(
            name="DAAD Scholarship",
            provider="DAAD Germany",
            source_type=SourceType.GOVERNMENT,
            country="Germany",
            degree_levels=["masters"],
            funding_type=FundingType.FULL,
        )
        assert opp.id is not None
        assert opp.name == "DAAD Scholarship"

    def test_eligibility_assessment_defaults(self):
        ea = EligibilityAssessment(
            scholarship_id="test-id",
            student_id="student-id",
            status=EligibilityStatus.NEEDS_VERIFICATION,
            confidence=0.5,
        )
        assert ea.confidence == 0.5
        assert ea.missing_documents == []

    def test_eligibility_confidence_bounds(self):
        with pytest.raises(ValidationError):
            EligibilityAssessment(
                scholarship_id="x",
                student_id="y",
                status=EligibilityStatus.ELIGIBLE,
                confidence=1.5,  # > 1.0 — invalid
            )

    def test_match_result_score_bounds(self):
        with pytest.raises(ValidationError):
            MatchResult(
                scholarship_id="x",
                student_id="y",
                rank=1,
                match_score=150.0,  # > 100 — invalid
                eligibility_status=EligibilityStatus.ELIGIBLE,
                eligibility_confidence=0.8,
            )


class TestWorkflowModels:
    def test_agent_event_creation(self):
        ev = AgentEvent(
            run_id="run-1",
            agent_name="profiler",
            status=AgentStatus.RUNNING,
            message="Starting profiler",
        )
        assert ev.id is not None
        assert ev.timestamp is not None

    def test_workflow_run_defaults(self):
        run = WorkflowRun(id="run-1", student_id="student-1")
        assert run.status == RunStatus.QUEUED
        assert run.opportunities_found == 0


class TestApplicationDraft:
    def test_draft_always_marked_as_draft(self):
        draft = ApplicationDraft(
            run_id="run-1",
            student_id="student-1",
            scholarship_id="sch-1",
            scholarship_name="Test Scholarship",
            draft_text="Sample SOP text [FULL_NAME]",
            placeholders=["FULL_NAME"],
        )
        assert draft.is_draft is True

    def test_draft_captures_placeholders(self):
        draft = ApplicationDraft(
            run_id="run-1",
            student_id="student-1",
            scholarship_id="sch-1",
            scholarship_name="Test Scholarship",
            draft_text="Dear committee, I am [FULL_NAME], with [IELTS_SCORE].",
            placeholders=["FULL_NAME", "IELTS_SCORE"],
        )
        assert "FULL_NAME" in draft.placeholders
        assert "IELTS_SCORE" in draft.placeholders
