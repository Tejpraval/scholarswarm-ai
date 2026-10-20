"""Tests for the FastAPI endpoints."""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.student import DEMO_PROFILE
from app.services import run_manager


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "ScholarSwarm" in data["service"]

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200


class TestProfileEndpoints:
    def test_create_profile(self, client):
        profile_data = {
            "name": "Test Student",
            "nationality": "Indian",
            "degree_level": "bachelors",
            "cgpa": 8.0,
            "destination_preferences": ["Canada", "Germany"],
            "target_degree": "masters",
            "funding_preference": "full_funding",
        }
        response = client.post("/api/profiles", json=profile_data)
        assert response.status_code == 201
        data = response.json()
        assert "profile_id" in data
        assert data["profile"]["name"] == "Test Student"

    def test_get_demo_profile(self, client):
        response = client.get("/api/profiles/demo")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Rahul Sharma"

    def test_get_nonexistent_profile_returns_404(self, client):
        response = client.get("/api/profiles/nonexistent-id-12345")
        assert response.status_code == 404

    def test_profile_name_required(self, client):
        response = client.post("/api/profiles", json={"email": "test@test.com"})
        assert response.status_code == 422  # Validation error

    def test_invalid_cgpa_rejected(self, client):
        response = client.post("/api/profiles", json={
            "name": "Test",
            "cgpa": 15.0,  # Invalid: > 10
            "cgpa_scale": 10.0,
        })
        # Should return 422 validation error
        assert response.status_code == 422


class TestDocumentUpload:
    def test_upload_invalid_content_type(self, client):
        """Only PDFs should be accepted."""
        with patch("app.services.database.get_student_profile", return_value=DEMO_PROFILE.dict()):
            response = client.post(
                f"/api/profiles/{DEMO_PROFILE.id}/documents",
                data={"doc_type": "resume"},
                files={"file": ("test.txt", b"some text content", "text/plain")},
            )
        assert response.status_code == 400

    def test_upload_empty_file_rejected(self, client):
        with patch("app.services.database.get_student_profile", return_value=DEMO_PROFILE.dict()):
            response = client.post(
                f"/api/profiles/{DEMO_PROFILE.id}/documents",
                data={"doc_type": "resume"},
                files={"file": ("test.pdf", b"", "application/pdf")},
            )
        assert response.status_code == 400

    def test_upload_invalid_pdf_contents_rejected(self, client):
        with patch("app.services.database.get_student_profile", return_value=DEMO_PROFILE.model_dump(mode="json")):
            response = client.post(
                f"/api/profiles/{DEMO_PROFILE.id}/documents",
                data={"doc_type": "resume"},
                files={"file": ("fake.pdf", b"this is not a PDF", "application/pdf")},
            )
        assert response.status_code == 400
        assert "valid PDF" in response.json()["detail"]

    def test_upload_over_ten_megabytes_rejected(self, client):
        payload = b"%PDF-1.4\n" + b"x" * (10 * 1024 * 1024)
        with patch("app.services.database.get_student_profile", return_value=DEMO_PROFILE.model_dump(mode="json")):
            response = client.post(
                f"/api/profiles/{DEMO_PROFILE.id}/documents",
                data={"doc_type": "resume"},
                files={"file": ("oversized.pdf", payload, "application/pdf")},
            )
        assert response.status_code == 413

    def test_upload_invalid_doc_type(self, client):
        with patch("app.services.database.get_student_profile", return_value=DEMO_PROFILE.dict()):
            response = client.post(
                f"/api/profiles/{DEMO_PROFILE.id}/documents",
                data={"doc_type": "invalid_type"},
                files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
            )
        assert response.status_code == 400


class TestRunEndpoints:
    def test_start_run_with_demo_profile(self, client):
        with patch("app.services.run_manager.start_run", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = "test-run-id-123"
            response = client.post("/api/runs", json={"profile_id": "demo"})

        assert response.status_code == 202
        data = response.json()
        assert "run_id" in data

    def test_start_run_nonexistent_profile(self, client):
        with patch("app.services.database.get_student_profile", return_value=None):
            response = client.post("/api/runs", json={"profile_id": "nonexistent-id"})
        assert response.status_code == 404

    def test_get_run_not_found(self, client):
        with patch("app.services.run_manager.get_run_status", return_value=None):
            response = client.get("/api/runs/nonexistent-run")
        assert response.status_code == 404

    def test_get_results_for_running_run(self, client):
        with patch("app.services.run_manager.get_run_results", return_value=None), \
             patch("app.services.run_manager.get_run_status",
                   return_value={"status": "running", "id": "test-run"}):
            response = client.get("/api/runs/test-run/results")
        assert response.status_code == 202

    def test_persisted_partial_results_keep_error_and_only_verified_top_matches(self, monkeypatch):
        run_id = "persisted-partial-run"
        opportunity = {
            "id": "unverified-award", "name": "Unverified award",
            "verification_status": "partial",
        }
        match = {
            "id": "match-1", "rank": 1, "eligibility_status": "potentially_eligible",
            "scholarship": {**opportunity, "verification_status": "verified"},
            "eligibility": {
                "disqualifying_factors": [],
                "requirement_checks": [{"status": "not_met"}],
            },
        }
        monkeypatch.setattr(run_manager, "_run_states", {})
        with patch("app.services.database.get_scholarships_for_run", return_value=[opportunity]), \
             patch("app.services.database.get_match_results_for_run", return_value=[match]), \
             patch("app.services.database.get_sop_draft", return_value=None), \
             patch("app.services.database.get_workflow_run", return_value={
                 "status": "partial", "workflow_error": "Official source evidence incomplete.",
                 "research_error": "One query failed.",
             }):
            result = run_manager.get_run_results(run_id)
        assert result["workflow_error"] == "Official source evidence incomplete."
        assert result["research_error"] == "One query failed."
        assert result["top_matches"] == []

    def test_retry_non_failed_run_returns_error(self, client):
        with patch("app.services.run_manager.get_run_status",
                   return_value={"status": "running", "id": "test-run"}):
            response = client.post("/api/runs/test-run/retry")
        assert response.status_code == 400

    def test_api_never_exposes_file_paths(self, client):
        """Document upload response must not expose server file paths."""
        import io
        minimal_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        with patch("app.services.database.get_student_profile", return_value=DEMO_PROFILE.dict()), \
             patch("app.utils.pdf_extractor.extract_text_safe", return_value=("extracted text", None)):
            response = client.post(
                f"/api/profiles/{DEMO_PROFILE.id}/documents",
                data={"doc_type": "resume"},
                files={"file": ("resume.pdf", minimal_pdf, "application/pdf")},
            )
        if response.status_code == 200:
            data = response.json()
            assert "file_path" not in data
            assert "extracted_text" not in data


def test_curated_demo_api_persists_evidence_results_events_and_sop(tmp_path, monkeypatch):
    from app.services import database
    from app.services.demo_dataset import load_fixture
    from app.agents import matcher
    import time

    def forbidden_provider_call(*args, **kwargs):
        raise AssertionError("Curated demo endpoint attempted a live LLM call")

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "demo.sqlite"))
    monkeypatch.setattr(matcher, "call_llm", forbidden_provider_call)
    profile = load_fixture()["demo_profile"]
    with TestClient(app) as demo_client:
        created = demo_client.post("/api/profiles", json=profile)
        assert created.status_code == 201, created.text
        profile_id = created.json()["profile_id"]

        started = demo_client.post("/api/demo/runs", json={"profile_id": profile_id})
        assert started.status_code == 202, started.text
        run_id = started.json()["run_id"]
        assert started.json()["mode"] == "curated_demo"

        for _ in range(100):
            status = demo_client.get(f"/api/runs/{run_id}").json()
            if status.get("status") in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert status["status"] == "completed"
        results = demo_client.get(f"/api/runs/{run_id}/results").json()
        assert results["run_mode"] == "curated_demo"
        assert results["discovered_count"] == 3
        assert len(results["top_matches"]) == 1
        assert len(results["all_matches"]) == 3
        assert results["sop_draft"]["is_draft"] is True
        assert "fictional demonstration profile" in results["sop_draft"]["warnings"][0]

        events = demo_client.get(f"/api/runs/{run_id}/events").text
        assert "curated_demo_fixture" in events
        assert "no AI provider calls" in events
        detail_id = results["top_matches"][0]["scholarship_id"]
        detail = demo_client.get(f"/api/runs/{run_id}/scholarships/{detail_id}").json()
        assert detail["scholarship"]["official_source_status"] == "verified"
        assert detail["eligibility"]["status"] == "eligible"
        sop = demo_client.post(f"/api/runs/{run_id}/sop")
        assert sop.status_code == 200
        assert sop.json()["scholarship_name"] == results["top_matches"][0]["scholarship"]["name"]


def test_demo_endpoint_refuses_unmatched_profile_without_fallback(client):
    created = client.post("/api/profiles", json={
        "name": "Different student",
        "nationality": "Indian",
        "degree_level": "bachelors",
        "degree_name": "B.Tech CS",
        "graduation_year": 2024,
        "target_degree": "masters",
        "destination_preferences": ["Australia"],
        "personal_statement_notes": "No offer is recorded.",
    })
    profile_id = created.json()["profile_id"]
    response = client.post("/api/demo/runs", json={"profile_id": profile_id})
    assert response.status_code == 422
    assert "choose Live Research" in response.json()["detail"]
