"""System API router - health, stats, settings, personas."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import psutil
from pathlib import Path

from personas import get_persona_manager, activate_persona, deactivate_persona, get_agent_name

router = APIRouter(prefix="/api", tags=["system"])


class SettingsUpdate(BaseModel):
    workspace_path: str | None = None
    github_username: str | None = None
    github_token: str | None = None


class PersonaActivateRequest(BaseModel):
    persona_id: str


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "sharrowkin-backend",
        "version": "0.1.0"
    }


@router.get("/stats")
async def get_system_stats():
    """Get system resource statistics."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        return {
            "cpu": {
                "percent": cpu_percent,
                "count": psutil.cpu_count()
            },
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent,
                "used": memory.used
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent
            }
        }
    except Exception as e:
        return {
            "error": str(e),
            "cpu": {"percent": 0, "count": 0},
            "memory": {"total": 0, "available": 0, "percent": 0, "used": 0},
            "disk": {"total": 0, "used": 0, "free": 0, "percent": 0}
        }


@router.get("/settings")
async def get_settings():
    """Get current settings."""
    workspace_path = os.getenv("WORKSPACE_PATH", "")

    # If not in env, try to detect from current directory
    if not workspace_path:
        workspace_path = str(Path.cwd())

    return {
        "workspace_path": workspace_path,
        "github_username": os.getenv("GITHUB_USERNAME", ""),
        "github_token": os.getenv("GITHUB_TOKEN", ""),
    }


@router.post("/settings")
async def update_settings(settings: SettingsUpdate):
    """Update settings."""
    updated = {}

    if settings.workspace_path:
        os.environ["WORKSPACE_PATH"] = settings.workspace_path
        updated["workspace_path"] = settings.workspace_path

    if settings.github_username:
        os.environ["GITHUB_USERNAME"] = settings.github_username
        updated["github_username"] = settings.github_username

    if settings.github_token:
        os.environ["GITHUB_TOKEN"] = settings.github_token
        updated["github_token"] = "***"  # Don't return token

    return {
        "success": True,
        "updated": updated
    }


@router.get("/personas")
async def list_personas():
    """List available personas."""
    manager = get_persona_manager()
    personas = []

    for persona_id, persona in manager.personas.items():
        personas.append({
            "id": persona_id,
            "name": persona.name,
            "description": persona.description,
            "emoji": persona.emoji,
            "active": manager.active_persona == persona_id
        })

    return personas


@router.get("/personas/active")
async def get_active_persona():
    """Get currently active persona."""
    manager = get_persona_manager()

    if not manager.active_persona:
        return {"active": None}

    persona = manager.personas.get(manager.active_persona)
    if not persona:
        return {"active": None}

    return {
        "active": {
            "id": manager.active_persona,
            "name": persona.name,
            "description": persona.description,
            "emoji": persona.emoji
        }
    }


@router.post("/personas/activate")
async def activate_persona_endpoint(request: PersonaActivateRequest):
    """Activate a persona."""
    try:
        activate_persona(request.persona_id)
        return {
            "success": True,
            "persona_id": request.persona_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/personas/deactivate")
async def deactivate_persona_endpoint():
    """Deactivate current persona."""
    deactivate_persona()
    return {"success": True}


@router.get("/personas/agent-name")
async def get_agent_name_endpoint():
    """Get current agent name (based on active persona)."""
    name = get_agent_name()
    return {"name": name}


@router.get("/cognitive/state")
async def get_cognitive_state():
    """Get current cognitive state (memory, phase, etc)."""
    return {
        "phase": "idle",
        "memory": {
            "dsm_nodes": 0,
            "rld_genes": 0,
            "cache_hit_rate": 0.0
        },
        "workspace": {
            "cached": False,
            "last_scan": None
        }
    }


@router.get("/keys")
async def get_api_keys():
    """Get API keys status (masked)."""
    return {
        "gemini": {
            "configured": bool(os.getenv("GEMINI_API_KEY")),
            "value": "***" if os.getenv("GEMINI_API_KEY") else None
        },
        "github": {
            "configured": bool(os.getenv("GITHUB_TOKEN")),
            "value": "***" if os.getenv("GITHUB_TOKEN") else None
        }
    }


@router.get("/deployment")
async def get_deployment_info():
    """Get deployment information."""
    return {
        "environment": os.getenv("ENVIRONMENT", "development"),
        "version": "1.0.0",
        "backend_url": "http://127.0.0.1:8000",
        "frontend_url": "http://localhost:3000"
    }
