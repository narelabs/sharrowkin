"""API routers for Sharrowkin backend."""

from .github import router as github_router
from .agent import router as agent_router
from .system import router as system_router

__all__ = [
    "github_router",
    "agent_router",
    "system_router",
]
