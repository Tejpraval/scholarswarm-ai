"""ScholarSwarm AI — FastAPI application entry point."""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Load environment variables — check backend/.env and project root .env
from pathlib import Path as _Path
_here = _Path(__file__).resolve().parent.parent  # backend/
load_dotenv(_here / ".env")                       # backend/.env (preferred)
load_dotenv(_here.parent / ".env")                # project root .env (fallback)
load_dotenv()                                     # cwd fallback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("ScholarSwarm AI starting up...")

    # Initialize database
    from app.services.database import init_db, mark_interrupted_runs_failed
    init_db()
    interrupted = mark_interrupted_runs_failed()
    if interrupted:
        logger.warning("Marked %s interrupted workflow run(s) as failed after restart", interrupted)

    # Ensure upload directory exists
    upload_dir = Path(os.getenv("UPLOAD_DIR", "uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Validate required env vars (warn, don't fail — allow demo mode)
    missing = []
    placeholder_markers = ("your_", "_here", "placeholder", "replace_me")
    for key in ("GEMINI_API_KEY", "TAVILY_API_KEY"):
        value = os.getenv(key, "").strip().strip("\"'")
        if not value or any(marker in value.lower() for marker in placeholder_markers):
            missing.append(key)
    if missing:
        logger.warning(
            f"Missing or placeholder environment variables: {', '.join(missing)}. "
            "Live research will not work. Set real API keys in backend/.env."
        )
    else:
        logger.info("API keys configured — live research enabled")

    logger.info("ScholarSwarm AI ready")
    yield
    logger.info("ScholarSwarm AI shutting down...")


app = FastAPI(
    title="ScholarSwarm AI",
    description="Multi-agent scholarship discovery and application assistant",
    version="1.0.0",
    lifespan=lifespan,
    # Disable automatic error detail exposure
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — allow the local frontend and the URL configured for deployments.
_allowed_frontend_origins = {
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
}
_configured_frontend = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
if _configured_frontend:
    _allowed_frontend_origins.add(_configured_frontend)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_allowed_frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
from app.api.routes import router
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {
        "service": "ScholarSwarm AI",
        "status": "running",
        "docs": "/api/docs",
        "health": "/api/health",
    }
