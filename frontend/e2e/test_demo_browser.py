"""Playwright smoke test for the full curated demo path.

Run from the repository root with:
    python -m pytest frontend/e2e/test_demo_browser.py -q

Requires Playwright's Python package and Microsoft Edge installed locally.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
def wait_for_url(url: str, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before becoming ready: {url}")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.2)
    raise TimeoutError(f"Service did not become ready: {url}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Fictional demo resume. Do not use as a real application document.")
    content = document.tobytes()
    document.close()
    return content


def test_curated_demo_browser_flow(tmp_path):
    api_port = free_port()
    web_port = free_port()

    backend_env = os.environ.copy()
    backend_env.update({
        "DB_PATH": str(tmp_path / "browser-demo.sqlite"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
        "GEMINI_API_KEY": "",
        "TAVILY_API_KEY": "",
        "BACKEND_HOST": "127.0.0.1",
        "BACKEND_PORT": str(api_port),
        "FRONTEND_URL": f"http://127.0.0.1:{web_port}",
    })
    Path(backend_env["UPLOAD_DIR"]).mkdir(parents=True)
    backend_log = (tmp_path / "backend.log").open("w", encoding="utf-8")
    frontend_log = (tmp_path / "frontend.log").open("w", encoding="utf-8")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
        cwd=BACKEND,
        env=backend_env,
        stdout=backend_log,
        stderr=subprocess.STDOUT,
    )
    frontend_env = os.environ.copy()
    frontend_env["VITE_API_URL"] = f"http://127.0.0.1:{api_port}/api"
    frontend_cmd = ["npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"]
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=FRONTEND,
        env=frontend_env,
        stdout=frontend_log,
        stderr=subprocess.STDOUT,
    )
    page_errors: list[str] = []
    failed_requests: list[str] = []
    http_errors: list[tuple[int, str]] = []
    event_stream_requests: list[str] = []

    try:
        wait_for_url(f"http://127.0.0.1:{api_port}/api/health", backend_proc)
        wait_for_url(f"http://127.0.0.1:{web_port}/", frontend_proc)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.on("requestfailed", lambda request: failed_requests.append(f"{request.method} {request.url}: {request.failure}"))
            page.on("request", lambda request: event_stream_requests.append(request.url) if request.url.endswith("/events") else None)
            page.on("response", lambda response: http_errors.append((response.status, response.url)) if response.status >= 400 else None)

            page.goto(f"http://127.0.0.1:{web_port}/", wait_until="networkidle")
            page.get_by_role("button", name="Load curated fictional profile — Maya Iyer").click()
            page.get_by_placeholder("University / College name").fill("Fictional Demo University - profile edited")
            page.get_by_role("button", name="Continue to Documents").click()
            page.get_by_role("button", name="Edit profile").click()
            page.get_by_placeholder("e.g. AI / Machine Learning").fill("Information Technology and Computer Science (edited)")
            page.get_by_role("button", name="Save Profile Changes").click()

            pdf = make_pdf()
            page.locator('input[type="file"]').nth(0).set_input_files({
                "name": "demo-resume.pdf", "mimeType": "application/pdf", "buffer": pdf,
            })
            page.get_by_text("Resume uploaded", exact=True).wait_for()
            page.locator('input[type="file"]').nth(1).set_input_files({
                "name": "invalid-marksheet.pdf", "mimeType": "application/pdf", "buffer": b"not a real PDF",
            })
            page.get_by_text("valid PDF header", exact=False).wait_for()
            page.locator('input[type="file"]').nth(1).set_input_files({
                "name": "demo-marksheet.pdf", "mimeType": "application/pdf", "buffer": pdf,
            })
            page.get_by_text("Marksheet uploaded", exact=True).wait_for()
            page.get_by_role("button", name="Find My Scholarships").click()

            page.get_by_test_id("active-mode").get_by_text("DEMO MODE").wait_for()
            page.get_by_text("Curated Fixture Progress", exact=True).wait_for()
            page.get_by_role("button", name="Load Curated Demo Results").click()
            page.get_by_test_id("curated-demo-banner").wait_for(timeout=15000)
            assert "not live AI discoveries" in page.get_by_test_id("curated-demo-banner").inner_text()
            assert "1 Recommended Opportunities" in page.locator("main").inner_text()
            assert page.get_by_role("heading", name="Vice-Chancellor's International Scholarships Scheme (Semester 1, 2027)").count() == 1

            page.get_by_role("heading", name="Vice-Chancellor's International Scholarships Scheme (Semester 1, 2027)").click()
            page.get_by_role("heading", name="Eligibility Checklist").wait_for()
            source_link = page.get_by_role("link", name="View fetched official source")
            assert source_link.get_attribute("href") == "https://www.sydney.edu.au/scholarships/e/vice-chancellors-international-scholarships-scheme.html"
            application_link = page.get_by_role("link", name="Official application route")
            assert application_link.get_attribute("href") == "https://www.sydney.edu.au/study/applying/how-to-apply/international-students.html"
            page.locator(".fixed.inset-0 button").click()

            page.get_by_role("button", name="All Found").click()
            assert page.get_by_text("Needs Verification", exact=True).count() == 2
            page.get_by_role("heading", name="University of Auckland International Student Excellence Scholarship (2027)").click()
            assert "No University of Auckland offer or invitation recorded" in page.locator(".fixed.inset-0").inner_text()
            page.locator(".fixed.inset-0 button").click()

            page.get_by_role("button", name="SOP Draft").click()
            page.get_by_text("Facts used from your profile", exact=True).wait_for()
            assert "Maya Iyer" in page.locator("main").inner_text()
            assert "fictional demonstration profile" in page.locator("main").inner_text()

            browser.close()

    finally:
        if os.name == "nt" and frontend_proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(frontend_proc.pid), "/T", "/F"], capture_output=True, check=False)
        for proc in (frontend_proc, backend_proc):
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        backend_log.close()
        frontend_log.close()

    assert page_errors == [], f"Browser page errors: {page_errors}"
    assert failed_requests == [], f"Failed browser requests: {failed_requests}"
    assert [status for status, _ in http_errors] == [400], f"Unexpected HTTP errors: {http_errors}"
    assert event_stream_requests, "Expected to observe the demo progress event stream request"
