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
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Setup structured logging with session_id correlation BEFORE any imports
# that might log during module load.
from core.logging_ctx import setup_logging
setup_logging()

# Import routers
from api import github_router, agent_router, system_router
from api.sessions import router as sessions_router
from api.routers.workspace import router as workspace_router

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

# Background task for session cleanup
import asyncio
from api.routers.agent import _cleanup_expired_sessions

async def periodic_session_cleanup():
    """Background task to clean up expired sessions every 5 minutes."""
    while True:
        await asyncio.sleep(300)  # 5 minutes
        try:
            _cleanup_expired_sessions()
        except Exception as e:
            print(f"[Session Cleanup] Error: {e}")

@app.on_event("startup")
async def startup_event():
    """Start background tasks on startup."""
    asyncio.create_task(periodic_session_cleanup())
    print("[Startup] Session cleanup task started")

# Include routers
app.include_router(github_router)
app.include_router(agent_router)
app.include_router(system_router)
app.include_router(sessions_router, prefix="/api/sessions")
app.include_router(workspace_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Sharrowkin Agent",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": {
            "sessions": "/api/sessions",
            "workspace_stats": "/api/workspace/stats",
            "github": "/api/github",
            "agent": "/api/agent"
        }
    }


if __name__ == "__main__":
    import uvicorn
    # When packaged as a standalone executable (PyInstaller sidecar), the
    # auto-reloader must be off — it would spawn orphan supervisor processes
    # and the import-string form ("main:app") doesn't resolve in a frozen app.
    is_frozen = getattr(sys, "frozen", False)
    uvicorn.run(
        app if is_frozen else "main:app",
        host="127.0.0.1",
        port=8000,
        reload=not is_frozen,
        ws_ping_interval=30.0,  # Send ping every 30 seconds
        ws_ping_timeout=300.0,  # Wait 5 minutes for pong response
        timeout_keep_alive=300  # Keep connection alive for 5 minutes
    )