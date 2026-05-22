"""Session API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.sessions import get_session_manager
from typing import List

router = APIRouter(tags=["sessions"])


class SessionImport(BaseModel):
    id: str
    label: str


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    task: str
    status: str
    workspace_path: str
    model: str
    message_count: int


@router.post("/import")
async def import_sessions(sessions: List[SessionImport]):
    """Import sessions from frontend localStorage."""
    from datetime import datetime

    session_manager = get_session_manager()
    imported_count = 0

    for s in sessions:
        # Check if session already exists
        if session_manager.get_session(s.id):
            continue

        # Create session
        now = datetime.utcnow().isoformat() + "Z"
        from backend.sessions import Session

        session = Session(
            id=s.id,
            title=s.label,
            created_at=now,
            updated_at=now,
            task=s.label,
            status="completed",
            workspace_path="/tmp/sharrowkin-workspace",
            model="gemini-2.0-flash-exp",
            message_count=0
        )

        session_manager.sessions[s.id] = session
        imported_count += 1

    session_manager._save_sessions()

    return {
        "status": "success",
        "imported": imported_count,
        "total": len(sessions)
    }


@router.get("/")
async def list_sessions(limit: int = 50):
    """List all sessions."""
    session_manager = get_session_manager()
    sessions = session_manager.list_sessions(limit=limit)

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "task": s.task,
                "status": s.status,
                "workspace_path": s.workspace_path,
                "model": s.model,
                "message_count": s.message_count
            }
            for s in sessions
        ]
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session by ID."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "task": session.task,
        "status": session.status,
        "workspace_path": session.workspace_path,
        "model": session.model,
        "message_count": session.message_count
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_manager.delete_session(session_id)

    return {"status": "success", "message": f"Session {session_id} deleted"}
