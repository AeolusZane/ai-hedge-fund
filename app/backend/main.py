from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import asyncio

# Load .env at import time so every code path (executors, services) sees
# the same view of credentials regardless of how uvicorn was launched.
load_dotenv()

from app.backend.routes import api_router
from app.backend.database.connection import engine
from app.backend.database.models import Base
from app.backend.services.ollama_service import ollama_service

# Importing each domain's `pack` module triggers its executor registration.
# The `pack` indirection keeps registration out of the package __init__,
# so e.g. `domains.finance.agents.*` can be imported without dragging the
# schemas → executor → schemas cycle into the import graph.
import app.backend.domains.finance.pack  # noqa: F401
import app.backend.domains.bug_fix.pack  # noqa: F401

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Hedge Fund API", description="Backend API for AI Hedge Fund", version="0.1.0")

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
                    "VARCHAR(64) NOT NULL DEFAULT 'finance'"
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

@app.on_event("startup")
async def startup_event():
    """Startup event to check Ollama availability."""
    try:
        logger.info("Checking Ollama availability...")
        status = await ollama_service.check_ollama_status()
        
        if status["installed"]:
            if status["running"]:
                logger.info(f"✓ Ollama is installed and running at {status['server_url']}")
                if status["available_models"]:
                    logger.info(f"✓ Available models: {', '.join(status['available_models'])}")
                else:
                    logger.info("ℹ No models are currently downloaded")
            else:
                logger.info("ℹ Ollama is installed but not running")
                logger.info("ℹ You can start it from the Settings page or manually with 'ollama serve'")
        else:
            logger.info("ℹ Ollama is not installed. Install it to use local models.")
            logger.info("ℹ Visit https://ollama.com to download and install Ollama")
            
    except Exception as e:
        logger.warning(f"Could not check Ollama status: {e}")
        logger.info("ℹ Ollama integration is available if you install it later")
