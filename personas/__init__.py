"""Persona system for thematic agent customization."""

from .system import (
    PersonaConfig,
    PersonaManager,
    activate_persona,
    deactivate_persona,
    format_log,
    get_agent_name,
    get_persona_manager,
    inject_persona,
)

__all__ = [
    "PersonaConfig",
    "PersonaManager",
    "get_persona_manager",
    "activate_persona",
    "deactivate_persona",
    "inject_persona",
    "format_log",
    "get_agent_name",
]
