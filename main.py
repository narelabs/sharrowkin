"""FastAPI entrypoint for Sharrowkin Agent.

Clean, modular architecture with organized routers.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Fix stdout encoding for Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Create a dummy backend module so absolute imports from 'backend' work
import types
if 'backend' not in sys.modules:
    backend_pkg = types.ModuleType('backend')
    backend_pkg.__path__ = [str(BACKEND_DIR)]
    sys.modules['backend'] = backend_pkg

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from api import github_router, agent_router, system_router
from api.sessions import router as sessions_router

# Create FastAPI app
app = FastAPI(
    title="Sharrowkin Agent API",
    version="1.0.0",
    description="AI-powered development agent with 5-phase reasoning cycle"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(github_router)
app.include_router(agent_router)
app.include_router(system_router)
app.include_router(sessions_router, prefix="/api/sessions")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Sharrowkin Agent",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
