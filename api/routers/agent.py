"""Agent API router - WebSocket, status, control."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from pathlib import Path
import asyncio
import json

from agent import SharrowkinAgent, PHASES
from memory import MemoryBridge
from sessions import get_session_manager

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentTaskRequest(BaseModel):
    task: str
    workspace: str
    session_id: str | None = None


# Global agent state
_active_agents: dict[str, SharrowkinAgent] = {}


@router.get("/status")
async def get_agent_status():
    """Get agent status."""
    return {
        "active_sessions": len(_active_agents),
        "phases": PHASES
    }


@router.post("/stop")
async def stop_agent(session_id: str):
    """Stop a running agent."""
    if session_id in _active_agents:
        # Agent will be cleaned up when WebSocket closes
        del _active_agents[session_id]
        return {"success": True, "message": "Agent stopped"}

    raise HTTPException(status_code=404, detail="Agent not found")


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    """WebSocket endpoint for agent communication."""
    await websocket.accept()

    session_id = None
    agent = None

    try:
        # Wait for initial message with task
        data = await websocket.receive_text()
        message = json.loads(data)

        task = message.get("task")
        workspace_path = message.get("workspace")
        session_id = message.get("session_id", f"session_{len(_active_agents)}")

        if not task or not workspace_path:
            await websocket.send_json({
                "type": "error",
                "message": "Missing task or workspace"
            })
            await websocket.close()
            return

        # Initialize agent
        workspace = Path(workspace_path)
        if not workspace.exists():
            await websocket.send_json({
                "type": "error",
                "message": f"Workspace not found: {workspace_path}"
            })
            await websocket.close()
            return

        # Create agent (no workspace parameter in __init__)
        agent = SharrowkinAgent()
        _active_agents[session_id] = agent

        # Send start event
        await websocket.send_json({
            "type": "agent_start",
            "session_id": session_id,
            "task": task,
            "workspace": str(workspace)
        })

        # Run agent and stream events (pass workspace_path as string)
        async for event in agent.run(task, workspace_path=str(workspace)):
            try:
                await websocket.send_json(event)
            except Exception as e:
                print(f"[WebSocket] Error sending event: {e}")
                break

        # Send completion
        await websocket.send_json({
            "type": "agent_complete",
            "session_id": session_id
        })

    except WebSocketDisconnect:
        print(f"[WebSocket] Client disconnected: {session_id}")
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        # Cleanup
        if session_id and session_id in _active_agents:
            del _active_agents[session_id]

        try:
            await websocket.close()
        except:
            pass
