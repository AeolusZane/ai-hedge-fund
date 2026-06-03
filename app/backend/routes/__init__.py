"""Routes package for AI Agent Platform API."""

from .health import router as health_router
from .storage import router as storage_router
from .api_keys import router as api_keys_router
from .experiences import router as experiences_router
from .bug_fix_dashboard import router as bug_fix_router

__all__ = [
    "health_router",
    "storage_router",
    "api_keys_router",
    "experiences_router",
    "bug_fix_router",
]
