"""Session management for Sharrowkin Agent."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Session:
    """Represents an agent session."""
    id: str
    title: str
    created_at: str
    updated_at: str
    task: str
    status: str  # "running", "completed", "failed"
    workspace_path: str
    model: str
    message_count: int = 0


class SessionManager:
    """Manages agent sessions."""

    def __init__(self, sessions_dir: str = "/tmp/sharrowkin-workspace/sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_file = self.sessions_dir / "sessions.json"
        self._load_sessions()

    def _load_sessions(self):
        """Load sessions from disk."""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.sessions = {s["id"]: Session(**s) for s in data}
            except Exception as e:
                print(f"[SessionManager] Failed to load sessions: {e}")
                self.sessions = {}
        else:
            self.sessions = {}

    def _save_sessions(self):
        """Save sessions to disk."""
        try:
            with open(self.sessions_file, "w", encoding="utf-8") as f:
                data = [asdict(s) for s in self.sessions.values()]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[SessionManager] Failed to save sessions: {e}")

    def create_session(
        self,
        session_id: str,
        task: str,
        workspace_path: str,
        model: str = "gemini-2.0-flash-exp"
    ) -> Session:
        """Create a new session with auto-generated title."""
        title = self._generate_title(task)
        now = datetime.utcnow().isoformat() + "Z"

        session = Session(
            id=session_id,
            title=title,
            created_at=now,
            updated_at=now,
            task=task,
            status="running",
            workspace_path=workspace_path,
            model=model,
            message_count=1
        )

        self.sessions[session_id] = session
        self._save_sessions()
        return session

    def update_session(
        self,
        session_id: str,
        status: Optional[str] = None,
        message_count: Optional[int] = None
    ):
        """Update session status and metadata."""
        if session_id not in self.sessions:
            return

        session = self.sessions[session_id]
        now = datetime.utcnow().isoformat() + "Z"
        session.updated_at = now

        if status:
            session.status = status
        if message_count is not None:
            session.message_count = message_count

        self._save_sessions()

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        return self.sessions.get(session_id)

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """List all sessions, sorted by updated_at (newest first)."""
        sessions = sorted(
            self.sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True
        )
        return sessions[:limit]

    def delete_session(self, session_id: str):
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._save_sessions()

    def _generate_title(self, task: str) -> str:
        """Generate a short title from task (max 60 chars)."""
        # Remove common prefixes
        task = task.strip()
        for prefix in ["создай", "создать", "добавь", "добавить", "исправь", "исправить",
                       "create", "add", "fix", "change", "modify", "write", "напиши"]:
            if task.lower().startswith(prefix):
                task = task[len(prefix):].strip()
                break

        # Truncate to 60 chars
        if len(task) > 60:
            task = task[:57] + "..."

        # Capitalize first letter
        if task:
            task = task[0].upper() + task[1:]

        return task or "New Session"


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
