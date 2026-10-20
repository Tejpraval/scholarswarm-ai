# ScholarSwarm AI — Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Browser)                         │
│                                                                     │
│   ┌─────────────┐   ┌──────────────────┐   ┌────────────────────┐ │
│   │  Onboarding  │   │  Agent Dashboard │   │  Results + SOP     │ │
│   │  (Profile    │   │  (Live SSE       │   │  (Scholarships,    │ │
│   │   + PDFs)    │   │   events)        │   │   Eligibility,     │ │
│   └─────┬───────┘   └────────┬─────────┘   │   Draft SOP)       │ │
│         │                    │              └────────────────────┘ │
└─────────┼────────────────────┼─────────────────────────────────────┘
          │ REST + SSE         │ EventSource
          ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND                              │
│                                                                     │
│   ┌──────────────┐   ┌──────────────┐   ┌─────────────────────┐  │
│   │  /profiles   │   │  /runs       │   │  /runs/{id}/events  │  │
│   │  /documents  │   │  /results    │   │  (SSE stream)       │  │
│   └──────┬───────┘   └──────┬───────┘   └──────────┬──────────┘  │
│          │                  │                       │              │
│          ▼                  ▼                       ▼              │
│   ┌──────────────────────────────────────────────────────────────┐ │
│   │                     Run Manager                              │ │
│   │  (asyncio task per run + event queues for SSE)               │ │
│   └──────────────────────────┬───────────────────────────────────┘ │
│                              │                                      │
│   ┌──────────────────────────▼───────────────────────────────────┐ │
│   │                  SQLite Database                             │ │
│   │  profiles | runs | scholarships | eligibility | matches | sop│ │
│   └──────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LANGGRAPH WORKFLOW                              │
│                                                                     │
│  GraphState (shared typed state across all agents)                  │
│                                                                     │
│  ┌──────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐   │
│  │ Profiler │───▶│ Researcher │───▶│ Verifier │───▶│ Matcher  │   │
│  │          │    │            │    │          │    │          │   │
│  │ • PDF    │    │ • 12 Tavily│    │ • Re-    │    │ • 6-     │   │
│  │   extract│    │   queries  │    │   search │    │   factor │   │
│  │ • GitHub │    │ • Gemini   │    │   each   │    │   score  │   │
│  │   API    │    │   parse    │    │   opp    │    │ • Top 5  │   │
│  │ • Profile│    │ • Dedup    │    │ • Per-   │    │ • SOP    │   │
│  │   enrich │    │            │    │   req    │    │   draft  │   │
│  └──────────┘    └────────────┘    │   check  │    └──────────┘   │
│       │               │            └──────────┘         │          │
│       │          [≥10 opps]        [assessments]    [matches+SOP]  │
│       │                                                             │
│  Conditional edges:                                                 │
│  • If no profile → stop with error                                  │
│  • If no opps found → skip to validate_output                       │
│  • If single verification fails → continue others                   │
│                                                                     │
│  ┌────────────────────┐                                             │
│  │  Output Validator  │ (checks evidence, source URLs, SOP)        │
│  └────────────────────┘                                             │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL APIs                                  │
│                                                                     │
│   Tavily Search API          Gemini API (LLM)       GitHub API     │
│   (web research)             (parse + reason)       (public repos)  │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. User submits profile via frontend
2. FastAPI creates StudentProfile, saves to SQLite
3. User uploads PDFs → extracted via PyMuPDF, text stored server-side
4. User clicks "Find My Scholarships" → POST /api/runs
5. Run Manager starts background asyncio task + SSE queue
6. LangGraph workflow executes:
   - **Profiler**: extracts PDF text via Gemini, fetches GitHub, computes completeness
   - **Researcher**: runs 12 Tavily queries, parses results via Gemini, deduplicates
   - **Verifier**: for each opportunity: re-searches Tavily, uses Gemini to check eligibility
   - **Matcher**: scores all opportunities, generates top 5 explanations via Gemini, drafts SOP
7. Each agent emits AgentEvent objects → queued for SSE delivery
8. Final state persisted to SQLite
9. Frontend EventSource receives events in real time, updates dashboard
10. Results page displays ranked opportunities with eligibility details

## Key Design Decisions

- **Shared GraphState**: All agents read from and write to a single Pydantic model — no side-channel communication
- **Evidence-first**: Every opportunity requires a source URL and source snippet — no fabrication
- **Separate score and eligibility**: Match score (0–100) reflects fit; eligibility status reflects verified requirements. A high score never implies confirmed eligibility
- **Bounded retries**: LLM and search calls retry up to 3x with exponential backoff; workflow continues even if individual opportunities fail
- **SSE over WebSocket**: Simpler, more reliable for unidirectional event streaming without a WebSocket library

## Security Measures

- PDF file paths never exposed in API responses
- Extracted text never returned in API responses
- API keys are server-side only
- File type and size validation on upload
- SQLite (not exposed externally)
- CORS restricted to known frontend origin
