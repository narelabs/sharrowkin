"""Migration script to import sessions from localStorage to backend."""

import json
from pathlib import Path
from datetime import datetime

# This script should be run once to migrate existing sessions
# from frontend localStorage to backend SessionManager

def migrate_sessions():
    """
    Instructions for migration:

    1. Open browser console (F12) on http://localhost:3000/chat
    2. Run this command to export sessions:
       console.log(JSON.stringify(localStorage.getItem('sharrowkin-sessions-list')))
    3. Copy the output
    4. Paste it into sessions_data variable below
    5. Run this script: python migrate_sessions.py
    """

    # Example format from localStorage:
    # [{"id":"session-1","label":"New agent session"},{"id":"session-2","label":"Fix auth bug"}]

    sessions_data = """
    PASTE_YOUR_SESSIONS_HERE
    """

    if "PASTE_YOUR_SESSIONS_HERE" in sessions_data:
        print("❌ Please paste your sessions data from localStorage first!")
        print("\nSteps:")
        print("1. Open http://localhost:3000/chat")
        print("2. Press F12 to open console")
        print("3. Run: console.log(JSON.stringify(localStorage.getItem('sharrowkin-sessions-list')))")
        print("4. Copy the output and paste it into this script")
        return

    try:
        sessions = json.loads(sessions_data)

        # Create sessions directory
        sessions_dir = Path("/tmp/sharrowkin-workspace/sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        sessions_file = sessions_dir / "sessions.json"

        # Convert to backend format
        backend_sessions = []
        now = datetime.utcnow().isoformat() + "Z"

        for s in sessions:
            backend_sessions.append({
                "id": s["id"],
                "title": s["label"],
                "created_at": now,
                "updated_at": now,
                "task": s["label"],  # Use label as task for now
                "status": "completed",
                "workspace_path": "/tmp/sharrowkin-workspace",
                "model": "gemini-2.0-flash-exp",
                "message_count": 0
            })

        # Save to backend
        with open(sessions_file, "w", encoding="utf-8") as f:
            json.dump(backend_sessions, f, indent=2, ensure_ascii=False)

        print(f"✅ Migrated {len(backend_sessions)} sessions to {sessions_file}")
        for s in backend_sessions:
            print(f"  - {s['id']}: {s['title']}")

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    migrate_sessions()
