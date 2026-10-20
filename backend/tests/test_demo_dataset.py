"""Curated demo fixture integrity and provider-independent execution tests."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.agents.matcher import _is_recommendable
from app.models.student import AcademicProfile, StudentProfile, DegreeLevel
from app.services.demo_dataset import build_demo_state, load_fixture, validate_demo_profile


def make_demo_profile(fixture=None):
    fixture = fixture or load_fixture()
    data = fixture["demo_profile"]
    return StudentProfile(
        id="demo-profile-test",
        name=data["name"],
        nationality=data["nationality"],
        academic=AcademicProfile(
            degree_level=DegreeLevel(data["degree_level"]),
            degree_name=data["degree_name"],
            institution=data["institution"],
            cgpa=data["cgpa"],
            cgpa_scale=data["cgpa_scale"],
            graduation_year=data["graduation_year"],
            major=data["major"],
        ),
        skills=data["skills"],
        research_interests=data["research_interests"],
        destination_preferences=data["destination_preferences"],
        target_degree=DegreeLevel(data["target_degree"]),
        target_field=data["target_field"],
        funding_preference=data["funding_preference"],
        personal_statement_notes=data["personal_statement_notes"],
    )


def test_curated_fixture_has_first_party_provenance_for_each_check():
    fixture = load_fixture()
    assert fixture["verified_on"] == "2026-10-20"
    assert len(fixture["opportunities"]) >= 3
    for opportunity in fixture["opportunities"]:
        provenance_urls = {source["url"] for source in opportunity["provenance"]["sources"]}
        assert opportunity["official_url"].startswith("https://")
        assert opportunity["verification_date"] == fixture["verified_on"]
        assert opportunity["application_url_status"]
        for check in opportunity["eligibility"]["checks"]:
            assert check["source_url"] in opportunity["official_source_urls"]
            assert check["source_url"] in provenance_urls
            if check["status"] in {"met", "not_met", "not_applicable"}:
                assert check["evidence"]
        assert opportunity["application_deadline"]


def test_demo_state_is_evidence_gated_and_generates_profile_fact_sop(monkeypatch):
    from app.agents import matcher

    def forbidden_provider_call(*args, **kwargs):
        raise AssertionError("Demo Mode must not call an LLM")

    monkeypatch.setattr(matcher, "call_llm", forbidden_provider_call)
    profile = make_demo_profile()
    state, fixture = asyncio.run(build_demo_state("demo-run-test", profile))

    assert len(state.discovered_opportunities) == 3
    assert len(state.top_matches) == 1
    assert state.top_matches[0].scholarship.id == "demo-sydney-vcis-2027"
    assert _is_recommendable(state.top_matches[0], profile)
    assert state.sop_draft is not None
    assert "Maya Iyer" in state.sop_draft.draft_text
    assert any("CGPA: 8.6/10.0" == fact for fact in state.sop_draft.facts_used)
    assert "fictional demonstration profile" in state.sop_draft.warnings[0]
    assert sum(match.eligibility_status.value == "needs_verification" for match in state.match_results) == 2


def test_demo_fixture_rejects_changed_critical_profile_facts():
    fixture = load_fixture()
    profile = make_demo_profile(fixture)
    profile.personal_statement_notes = "Offer unknown."
    missing = validate_demo_profile(profile, fixture)
    assert any("University of Sydney" in item for item in missing)
