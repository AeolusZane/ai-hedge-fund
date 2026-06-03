from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import logging
import asyncio
from pathlib import Path

# Load .env at import time so every code path (executors, services) sees
# the same view of credentials regardless of how uvicorn was launched.
load_dotenv()

from app.backend.routes import api_router
from app.backend.database.connection import engine
from app.backend.database.models import Base

# Importing each domain's `pack` module triggers its executor registration.
import app.backend.domains.bug_fix.pack  # noqa: F401

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Agent Platform API", description="Backend API for AI Agent Platform", version="0.2.0")

# Initialize database tables (this is safe to run multiple times)
Base.metadata.create_all(bind=engine)


def _ensure_flow_domain_column() -> None:
    """Idempotently add the `domain` column to existing SQLite databases.

    `create_all` only creates missing tables; it doesn't migrate existing
    ones. Production setups should use Alembic; this path keeps the dev
    DB up to date without forcing the user to nuke it.
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        cols = conn.execute(text("PRAGMA table_info(hedge_fund_flows)")).fetchall()
        if not any(row[1] == "domain" for row in cols):
            conn.execute(
                text(
                    "ALTER TABLE hedge_fund_flows ADD COLUMN domain "
                    "VARCHAR(64) NOT NULL DEFAULT 'bug_fix'"
                )
            )
            conn.commit()


_ensure_flow_domain_column()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routes
app.include_router(api_router)

# Serve frontend static files (SPA fallback)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="static-assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve index.html for all SPA routes"""
        # If the requested file exists in dist, serve it directly
        file_path = frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(frontend_dist / "index.html")

@app.on_event("startup")
async def startup_event():
    """Startup event."""
    logger.info("AI Agent Platform API started")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event."""
    logger.info("AI Agent Platform API stopped")
