# ScholarSwarm AI

**Evidence-aware scholarship discovery and application assistant**

> TetraNoodle AI Hackathon 2026 — Submission by [Team Name]
> Deadline: October 23, 2026 at 11:59 PM IST

---

## Overview

ScholarSwarm AI has two explicit modes. Live Research uses the LangGraph workflow, Gemini, and Tavily; results depend on those services and may be partial. Demo Mode loads a versioned, manually curated official-source fixture without calling AI providers. Demo data is labelled as curated and assessed against its documented fictional profile. Neither mode pads results to reach a recommendation count.

**Key capabilities:**
- Accepts resume/marksheet PDFs, academic profiles, and GitHub URLs
- Live scholarship discovery through Tavily and structured Gemini output
- Official-source verification with per-requirement evidence and explicit uncertainty
- Deterministic ranking that separates match score from confirmed eligibility
- SOP drafts use profile facts and visibly mark missing details
- Live agent dashboard via Server-Sent Events

---

## Architecture

```
Frontend (React + Vite + TypeScript + Tailwind)
        │
        ▼ REST API / SSE
Backend (FastAPI + Python)
        │
        ▼
LangGraph Workflow
┌───────────────────────────────────────────────┐
│  Profiler → Researcher → Verifier → Matcher   │
│       ↓          ↓           ↓         ↓      │
│  enriched   ≥10 opps   eligibility   top 5    │
│  profile    w/ source  assessments  + SOP     │
└───────────────────────────────────────────────┘
        │
        ▼
SQLite (runs + scholarships + assessments + events)
```

### Agent Roles

| Agent | Role | Key output |
|-------|------|-----------|
| Student Profiler | Validates profile, extracts from PDFs, enriches from GitHub | Structured StudentProfile |
| Scholarship Researcher | Runs 12 targeted Tavily searches, parses via Gemini | ≥10 ScholarshipOpportunity records |
| Eligibility Verifier | Re-searches each opportunity, checks requirements per-item | EligibilityAssessment per opportunity |
| Matching Agent | Transparent 6-factor scoring, generates SOP | MatchResult ranking + ApplicationDraft |

---

## Quick Start

### Prerequisites

- Python 3.10+ (tested on 3.13)
- Node.js 18+ and npm
- A [Gemini API key](https://aistudio.google.com/app/apikey)
- A [Tavily API key](https://tavily.com)

### 1. Clone and configure

```bash
git clone <repo-url>
cd agentic_ai_project

# Backend environment
cp .env.example backend/.env
# Add GEMINI_API_KEY and TAVILY_API_KEY only for Live Research.
```

### 2. Backend setup

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend will be available at: http://localhost:8000
API docs: http://localhost:8000/api/docs

### 3. Frontend setup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Frontend will be available at: http://localhost:5173

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes (live mode) | Google Gemini API key |
| `GEMINI_MODEL` | No | Default: `gemini-3.5-flash-lite` |
| `TAVILY_API_KEY` | Yes (live mode) | Tavily search API key |
| `DB_PATH` | No | SQLite database file path (default: `scholarswarm.db`) |
| `UPLOAD_DIR` | No | PDF upload directory (default: `uploads/`) |
| `VITE_API_URL` | No (frontend) | Backend API URL (default: `http://localhost:8000/api`) |

Choose **Demo Mode** or **Live Research** in the profile screen. Demo Mode is an evidence snapshot, not a live discovery run; its verification date appears in results. Live Research never falls back to demo data when a provider fails.

---

## Deployment

See [docs/deployment.md](docs/deployment.md) for the Render and Vercel settings, environment variables, persistent disk requirements, and acceptance checks.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/profiles` | Create student profile |
| GET | `/api/profiles/{id}` | Get profile (use `demo` for Rahul's profile) |
| PUT | `/api/profiles/{id}` | Update profile |
| POST | `/api/profiles/{id}/documents` | Upload PDF (resume/marksheet) |
| POST | `/api/runs` | Start research workflow |
| POST | `/api/demo/runs` | Load curated fixture without Gemini/Tavily calls (requires the matching fictional demo qualifications) |
| GET | `/api/runs/{id}` | Get run status |
| GET | `/api/runs/{id}/events` | SSE stream of agent events |
| GET | `/api/runs/{id}/results` | Get full results |
| GET | `/api/runs/{id}/scholarships/{sch_id}` | Get scholarship + eligibility detail |
| POST | `/api/runs/{id}/sop` | Retrieve SOP draft |
| POST | `/api/runs/{id}/retry` | Retry a failed run |

---

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

Tests are deterministic — all external APIs are mocked. Check the latest test output for actual counts; backend tests do not establish live provider availability.

---

## Curated Demo Profile

The curated fixture uses Maya Iyer, a **fictional** profile. Its Sydney offer, international status, and other qualifications are invented demo facts, clearly labelled in the application; they are not facts about a real applicant. The backend rejects the fixture run if key qualifications or offer facts are changed. Other fixture opportunities remain unresolved where the fictional profile lacks evidence.

The source snapshot is in `backend/app/demo_fixture/opportunities.json` and was checked on 20 October 2026. Current application pages can change; verify each linked source again before relying on it.

Use the demo profile from the frontend or via the API:
```bash
curl http://localhost:8000/api/profiles/demo
```

---

## Replacing the Demo Profile

No code changes required. Simply create a new profile:

```bash
curl -X POST http://localhost:8000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "Priya Patel", "nationality": "Indian", "degree_level": "masters",
       "cgpa": 9.1, "cgpa_scale": 10.0, "destination_preferences": ["USA", "UK"],
       "target_degree": "phd", "target_field": "Data Science",
       "funding_preference": "full_funding", "skills": ["Python", "R", "ML"]}'
```

Then start a run with the returned `profile_id`.

---

## Deployment Guide

### Backend (FastAPI)

**Local / VM:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Docker:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Environment variables** must be set via `.env` file or container environment.

### Frontend (React + Vite)

**Build:**
```bash
cd frontend
VITE_API_URL=https://your-backend.com/api npm run build
# Serve the dist/ folder with any static host (Nginx, Vercel, Netlify, etc.)
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `GEMINI_API_KEY not set` | Add key to `backend/.env` |
| `TAVILY_API_KEY not set` | Add key to `backend/.env` |
| No scholarships found | Check Tavily key, try demo profile first |
| Backend won't start | Check Python 3.10+, run `pip install -r requirements.txt` |
| Frontend won't connect | Ensure backend runs on port 8000, check CORS |
| PDF extraction fails | Install PyMuPDF: `pip install PyMuPDF` |
| SOP not generated | Ensure at least one opportunity was found and matched |

---

## Known Limitations

1. **No IELTS/TOEFL for Rahul**: All agents correctly flag this as a missing requirement
2. **LLM rate limits**: Gemini Flash may slow down on large opportunity sets; bounded retry handles this
3. **Search accuracy**: Tavily returns recent but not always official primary sources
4. **Deadline parsing**: Some deadline formats may not be parsed to a date (marked as unknown)
5. **GitHub placeholder**: Rahul's GitHub URL is a placeholder — real enrichment requires an actual profile

---

## Experiment Note

**Interesting finding:** When the Verifier agent independently re-searched opportunities that the Researcher had already found, it often discovered additional details (like specific CGPA thresholds or citizenship restrictions) that the Researcher's broader queries had missed. The two-pass approach added meaningful signal.

**Significant challenge:** LangGraph 0.2.x's `StateGraph` with Pydantic v2 models required careful handling of state mutation — Pydantic v2 objects are immutable by default, so agents use `model_copy(update=...)` rather than direct assignment. LangGraph's `ainvoke` also returns a dict that must be reconstructed into the typed state object.

---

## Five-Minute Demo Script

> The steps below were written for an earlier live-only workflow and are obsolete. Use the current Demo Mode flow described in [docs/deployment.md](docs/deployment.md) and the handover instructions; do not describe curated fixture progress as live agent activity.

1. **[0:00]** Open http://localhost:5173 — show the onboarding form
2. **[0:30]** Click "Use Demo Profile — Rahul Sharma" to load the pre-built demo
3. **[0:45]** Click "Continue" then "Find My Scholarships"
4. **[1:00]** Show the Agent Pipeline — 4 agents with real-time status updates
5. **[2:00]** While running, explain: "The Researcher is querying Tavily for real scholarships, the Verifier is independently checking eligibility, all via Gemini"
6. **[3:00]** Results page loads — show top 5 recommendations, note eligibility/score are separate
7. **[3:30]** Click one result — show the per-requirement eligibility checklist
8. **[4:00]** Switch to "SOP Draft" tab — show the generated statement with placeholders highlighted
9. **[4:30]** Explain: "IELTS is missing — the verifier flagged it, the SOP has a placeholder, the next actions remind Rahul to take the test"
10. **[5:00]** Go back, show the "All Found" tab and explain that only opportunities with cited first-party evidence are promoted as recommendations; counts can be below five when evidence is incomplete.

---

*This application was built for the TetraNoodle AI Hackathon 2026.*
*All student data is fictional. No actual applications are submitted.*
