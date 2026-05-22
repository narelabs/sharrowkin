"""Persona system for thematic LLM prompt customization.

This module provides a framework for injecting themed personalities into
the LLM prompts, creating unique agent experiences.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PersonaConfig:
    """Configuration for a themed persona."""

    id: str
    name: str
    agent_name: str = ""  # Name the agent uses when this persona is active
    description: str = ""

    # Visual theme
    colors: dict[str, str] = field(default_factory=dict)

    # LLM customization
    system_prompt_prefix: str = ""
    terminology: dict[str, str] = field(default_factory=dict)
    log_templates: dict[str, str] = field(default_factory=dict)

    # Audio
    audio_enabled: bool = True
    audio_files: dict[str, str] = field(default_factory=dict)

    # Metadata
    tags: list[str] = field(default_factory=list)
    author: str = "Sharrowkin Team"
    version: str = "1.0.0"

    @classmethod
    def from_json(cls, path: Path) -> PersonaConfig:
        """Load persona config from JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def to_json(self, path: Path) -> None:
        """Save persona config to JSON file."""
        data = {
            "id": self.id,
            "name": self.name,
            "agent_name": self.agent_name,
            "description": self.description,
            "colors": self.colors,
            "system_prompt_prefix": self.system_prompt_prefix,
            "terminology": self.terminology,
            "log_templates": self.log_templates,
            "audio_enabled": self.audio_enabled,
            "audio_files": self.audio_files,
            "tags": self.tags,
            "author": self.author,
            "version": self.version,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class PersonaManager:
    """Manages persona loading and application."""

    def __init__(self, personas_dir: Path | None = None) -> None:
        self.personas_dir = personas_dir or (Path(__file__).parent / "presets")
        self.personas: dict[str, PersonaConfig] = {}
        self.active_persona: PersonaConfig | None = None
        self._load_personas()

    def _load_personas(self) -> None:
        """Load all persona configs from directory."""
        if not self.personas_dir.exists():
            return

        for json_file in self.personas_dir.glob("*.json"):
            try:
                persona = PersonaConfig.from_json(json_file)
                self.personas[persona.id] = persona
            except Exception as e:
                print(f"Warning: Could not load persona from {json_file}: {e}")

    def get_persona(self, persona_id: str) -> PersonaConfig | None:
        """Get a persona by ID."""
        return self.personas.get(persona_id)

    def list_personas(self) -> list[PersonaConfig]:
        """Get all available personas."""
        return list(self.personas.values())

    def activate_persona(self, persona_id: str) -> bool:
        """Activate a persona."""
        persona = self.get_persona(persona_id)
        if persona:
            self.active_persona = persona
            return True
        return False

    def deactivate_persona(self) -> None:
        """Deactivate current persona (return to default)."""
        self.active_persona = None

    def inject_persona_prompt(self, base_prompt: str) -> str:
        """Inject persona customization into a prompt."""
        if not self.active_persona:
            return base_prompt

        # If persona is active, REPLACE identity completely with persona prefix
        # The persona prefix already contains full character identity
        customized = self.active_persona.system_prompt_prefix + "\n\n" + base_prompt

        # Replace terminology
        for standard_term, persona_term in self.active_persona.terminology.items():
            customized = customized.replace(standard_term, persona_term)

        return customized

    def format_log(self, log_type: str, message: str) -> str:
        """Format a log message with persona theming."""
        if not self.active_persona:
            return message

        template = self.active_persona.log_templates.get(log_type)
        if template:
            return template.format(message=message)

        return message

    def get_audio_file(self, event_type: str) -> str | None:
        """Get audio file path for an event type."""
        if not self.active_persona or not self.active_persona.audio_enabled:
            return None

        return self.active_persona.audio_files.get(event_type)

    def get_agent_name(self) -> str:
        """Get the current agent name based on active persona."""
        if self.active_persona and self.active_persona.agent_name:
            return self.active_persona.agent_name
        return "Sharrowkin"  # Default name


# Global persona manager instance
_persona_manager: PersonaManager | None = None


def get_persona_manager() -> PersonaManager:
    """Get the global persona manager instance."""
    global _persona_manager
    if _persona_manager is None:
        _persona_manager = PersonaManager()
    return _persona_manager


def activate_persona(persona_id: str) -> bool:
    """Activate a persona globally."""
    return get_persona_manager().activate_persona(persona_id)


def deactivate_persona() -> None:
    """Deactivate current persona globally."""
    get_persona_manager().deactivate_persona()


def inject_persona(prompt: str) -> str:
    """Inject active persona into a prompt."""
    return get_persona_manager().inject_persona_prompt(prompt)


def format_log(log_type: str, message: str) -> str:
    """Format a log with active persona."""
    return get_persona_manager().format_log(log_type, message)


def get_agent_name() -> str:
    """Get the current agent name based on active persona."""
    return get_persona_manager().get_agent_name()
