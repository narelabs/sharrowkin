"""API endpoints for persona management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from personas import get_persona_manager, activate_persona, deactivate_persona

router = APIRouter()


class PersonaActivateRequest(BaseModel):
    persona_id: str


@router.get("/personas")
async def list_personas():
    """Get all available personas."""
    manager = get_persona_manager()
    personas = manager.list_personas()

    return {
        "personas": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "colors": p.colors,
                "tags": p.tags,
                "audio_enabled": p.audio_enabled,
            }
            for p in personas
        ],
        "active_persona": manager.active_persona.id if manager.active_persona else None,
    }


@router.get("/personas/active")
async def get_active_persona():
    """Get the currently active persona."""
    manager = get_persona_manager()

    if manager.active_persona:
        return {
            "id": manager.active_persona.id,
            "name": manager.active_persona.name,
            "description": manager.active_persona.description,
            "colors": manager.active_persona.colors,
        }

    return {"id": None, "name": "Default", "description": "Standard Sharrowkin agent"}


@router.post("/personas/activate")
async def activate_persona_endpoint(request: PersonaActivateRequest):
    """Activate a persona."""
    success = activate_persona(request.persona_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Persona '{request.persona_id}' not found")

    return {
        "status": "success",
        "message": f"Persona '{request.persona_id}' activated",
        "persona_id": request.persona_id,
    }


@router.post("/personas/deactivate")
async def deactivate_persona_endpoint():
    """Deactivate the current persona."""
    deactivate_persona()

    return {
        "status": "success",
        "message": "Persona deactivated, using default agent",
    }
