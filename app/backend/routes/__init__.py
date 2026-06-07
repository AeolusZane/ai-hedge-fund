"""Routes package for AI Agent Platform API."""

from fastapi import APIRouter

from .health import router as health_router
from .storage import router as storage_router
from .api_keys import router as api_keys_router
from .experiences import router as experiences_router
from .bug_fix_dashboard import router as bug_fix_router
from .evolution import router as evolution_router

# Aggregate all routers into a single api_router for main.py
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(storage_router)
api_router.include_router(api_keys_router)
api_router.include_router(experiences_router)
api_router.include_router(bug_fix_router)
api_router.include_router(evolution_router)

# Include workflow routes from core
from app.backend.core.routes.workflows import router as workflows_router
api_router.include_router(workflows_router)

__all__ = [
    "api_router",
    "health_router",
    "storage_router",
    "api_keys_router",
    "experiences_router",
    "bug_fix_router",
    "evolution_router",
]
