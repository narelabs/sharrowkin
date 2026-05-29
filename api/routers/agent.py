"""Agent API router - WebSocket, status, control."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from pathlib import Path
import asyncio
import json
import uuid
import time

from agent import SharrowkinAgent, PHASES
from memory import MemoryBridge
from sessions import get_session_manager

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentTaskRequest(BaseModel):
    task: str
    workspace: str
    session_id: str | None = None


# Global agent state - PERSISTENT SESSIONS
# Format: {session_id: (agent, memory, last_used_timestamp)}
_agent_sessions: dict[str, tuple[SharrowkinAgent, MemoryBridge, float]] = {}
_active_agents: dict[str, SharrowkinAgent] = {}  # Keep for backward compatibility

# Thread-safety locks
_sessions_lock = asyncio.Lock()
_active_lock = asyncio.Lock()

# Session timeout: 4 hours (increased to prevent context loss)
SESSION_TIMEOUT = 14400


@router.get("/status")
async def get_agent_status():
    """Get agent status."""
    # Clean up expired sessions
    await _cleanup_expired_sessions()

    async with _sessions_lock:
        session_count = len(_agent_sessions)

    return {
        "active_sessions": session_count,
        "phases": PHASES
    }


async def _cleanup_expired_sessions():
    """Remove expired sessions with thread-safety."""
    current_time = time.time()
    async with _sessions_lock:
        expired = [
            sid for sid, (_, _, last_used) in _agent_sessions.items()
            if current_time - last_used > SESSION_TIMEOUT
        ]
        for sid in expired:
            del _agent_sessions[sid]
            print(f"[Session] Cleaned up expired session: {sid}")


@router.post("/session/clear")
async def clear_session(session_id: str):
    """Clear agent session and memory."""
    async with _sessions_lock:
        if session_id in _agent_sessions:
            del _agent_sessions[session_id]
            return {"success": True, "message": f"Session {session_id} cleared"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/session/info")
async def get_session_info(session_id: str):
    """Get session information."""
    async with _sessions_lock:
        if session_id not in _agent_sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        agent, memory, last_used = _agent_sessions[session_id]
        return {
            "session_id": session_id,
            "conversation_length": len(agent.conversation_history),
            "last_used": last_used,
            "age_seconds": time.time() - last_used
        }


@router.post("/stop")
async def stop_agent(session_id: str):
    """Stop a running agent."""
    async with _active_lock:
        if session_id in _active_agents:
            # Agent will be cleaned up when WebSocket closes
            del _active_agents[session_id]
            return {"success": True, "message": "Agent stopped"}

    raise HTTPException(status_code=404, detail="Agent not found")


@router.websocket("/ws")
async def agent_websocket(websocket: WebSocket):
    """WebSocket endpoint for agent communication."""
    print("[WebSocket] New connection attempt")
    await websocket.accept()
    print("[WebSocket] Connection accepted")

    session_id = None
    agent = None

    try:
        # Wait for initial message with task
        print("[WebSocket] Waiting for initial message...")
        data = await websocket.receive_text()
        print(f"[WebSocket] Received data: {data[:200]}...")
        message = json.loads(data)
        print(f"[WebSocket] Parsed message: task={message.get('task', '')[:50]}, workspace={message.get('workspace', '')}")

        task = message.get("task")
        workspace_path = message.get("workspace")
        session_id = message.get("session_id") or f"session_{uuid.uuid4().hex[:8]}"

        if not task or not workspace_path:
            print(f"[WebSocket] ERROR: Missing task or workspace. task={bool(task)}, workspace={bool(workspace_path)}")
            await websocket.send_json({
                "type": "error",
                "message": "Missing task or workspace"
            })
            await websocket.close()
            return

        # Initialize workspace
        workspace = Path(workspace_path)
        if not workspace.exists():
            print(f"[WebSocket] ERROR: Workspace not found: {workspace_path}")
            await websocket.send_json({
                "type": "error",
                "message": f"Workspace not found: {workspace_path}"
            })
            await websocket.close()
            return

        # ✅ FIX: Reuse existing agent session or create new one with thread-safety
        async with _sessions_lock:
            if session_id in _agent_sessions:
                agent, memory, _ = _agent_sessions[session_id]
                print(f"[Session] Reusing agent for session {session_id}")

                # ✅ NEW: Restore conversation history in agent
                if hasattr(agent, 'conversation') and agent.conversation:
                    conv_length = len(agent.conversation)
                else:
                    conv_length = len(agent.conversation_history)

                await websocket.send_json({
                    "type": "session_info",
                    "message": f"Continuing session {session_id}",
                    "conversation_length": conv_length
                })
            else:
                agent = SharrowkinAgent()
                memory = MemoryBridge(workspace)  # Pass Path object, not string
                print(f"[Session] Created new agent for session {session_id}")
                await websocket.send_json({
                    "type": "session_info",
                    "message": f"Started new session {session_id}"
                })

            # Update session timestamp
            _agent_sessions[session_id] = (agent, memory, time.time())

        async with _active_lock:
            _active_agents[session_id] = agent  # Backward compatibility

        # Send start event
        await websocket.send_json({
            "type": "agent_start",
            "session_id": session_id,
            "task": task,
            "workspace": str(workspace)
        })

        # ✅ NEW: Backpressure control with event queue
        event_queue = asyncio.Queue(maxsize=100)
        send_task = None

        async def send_events():
            """Background task to send events with backpressure control."""
            while True:
                try:
                    event = await event_queue.get()
                    if event is None:  # Sentinel to stop
                        break
                    await websocket.send_json(event)
                except Exception as e:
                    print(f"[WebSocket] Error sending event: {e}")
                    break

        # Start background sender
        send_task = asyncio.create_task(send_events())

        # Run agent and stream events (pass workspace_path as string)
        last_ping = time.time()
        async for event in agent.run(task, workspace_path=str(workspace)):
            try:
                # Try to put event in queue, drop oldest if full
                try:
                    event_queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest event and add new one
                    try:
                        event_queue.get_nowait()
                        event_queue.put_nowait(event)
                    except:
                        pass

                # Send heartbeat ping every 30 seconds to keep connection alive
                current_time = time.time()
                if current_time - last_ping > 30:
                    try:
                        heartbeat = {
                            "type": "heartbeat",
                            "timestamp": current_time
                        }
                        event_queue.put_nowait(heartbeat)
                        last_ping = current_time
                    except asyncio.QueueFull:
                        pass  # Skip heartbeat if queue is full
            except Exception as e:
                print(f"[WebSocket] Error queueing event: {e}")
                break

        # Wait for all events to be sent
        await event_queue.put(None)  # Sentinel
        if send_task:
            await send_task

        # Update session timestamp after completion
        async with _sessions_lock:
            if session_id in _agent_sessions:
                agent, memory, _ = _agent_sessions[session_id]
                _agent_sessions[session_id] = (agent, memory, time.time())

        # Send completion
        await websocket.send_json({
            "type": "agent_complete",
            "session_id": session_id
        })

    except WebSocketDisconnect:
        print(f"[WebSocket] Client disconnected: {session_id}")
    except Exception as e:
        import traceback
        print(f"[WebSocket] Error: {e}")
        print(f"[WebSocket] Full traceback:")
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        # ✅ FIX: DON'T delete agent session - keep for next request
        # Only remove from active agents (backward compatibility)
        if session_id:
            async with _active_lock:
                if session_id in _active_agents:
                    del _active_agents[session_id]

        try:
            await websocket.close()
        except:
            pass
