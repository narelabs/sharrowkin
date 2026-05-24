"""Session API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sessions import get_session_manager, Session, SessionAction

router = APIRouter()


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


class SessionActionResponse(BaseModel):
    timestamp: str
    phase: str
    action: str
    tool: Optional[str] = None
    result: Optional[str] = None


class SessionHistoryResponse(BaseModel):
    session_id: str
    actions: List[SessionActionResponse]
    total_actions: int


@router.get("/", response_model=List[SessionResponse])
async def list_sessions(limit: int = 50):
    """List all sessions."""
    manager = get_session_manager()
    sessions = manager.list_sessions(limit=limit)
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            task=s.task,
            status=s.status,
            workspace_path=s.workspace_path,
            model=s.model,
            message_count=s.message_count
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session by ID."""
    manager = get_session_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        task=session.task,
        status=session.status,
        workspace_path=session.workspace_path,
        model=session.model,
        message_count=session.message_count
    )


@router.get("/{session_id}/history", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str, limit: Optional[int] = None):
    """Get action history for a session."""
    manager = get_session_manager()
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    actions = session.actions
    if limit:
        actions = actions[-limit:]  # Get last N actions
    
    return SessionHistoryResponse(
        session_id=session_id,
        actions=[
            SessionActionResponse(
                timestamp=a.timestamp,
                phase=a.phase,
                action=a.action,
                tool=a.tool,
                result=a.result
            )
            for a in actions
        ],
        total_actions=len(session.actions)
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    manager = get_session_manager()
    manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.post("/import")
async def import_sessions(sessions: List[SessionImport]):
    """Import sessions from frontend."""
    return {"status": "imported", "count": len(sessions)}