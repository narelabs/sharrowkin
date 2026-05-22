"""Integration module for persona system with LLM.

This module provides helper functions to integrate persona theming
with the existing LLM pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .system import PersonaManager


def integrate_persona_with_llm(llm_module: object, persona_manager: PersonaManager) -> None:
    """Integrate persona system with LLM module.

    This patches the LLM module to automatically inject persona prompts.
    """
    original_generate = getattr(llm_module, 'generate_text', None)
    if not original_generate:
        return

    def generate_with_persona(prompt: str, system_instruction: str = "", **kwargs):
        """Wrapped generate_text that injects persona."""
        # Inject persona into system instruction
        if persona_manager.active_persona:
            system_instruction = persona_manager.inject_persona_prompt(system_instruction)

        return original_generate(prompt, system_instruction, **kwargs)

    # Monkey patch the method
    setattr(llm_module, 'generate_text', generate_with_persona)


def format_agent_log(log_type: str, message: str, persona_manager: PersonaManager) -> str:
    """Format an agent log message with persona theming.

    Args:
        log_type: Type of log (plan_start, file_write, test_pass, etc.)
        message: The log message content
        persona_manager: Active persona manager

    Returns:
        Formatted log message with persona theming
    """
    return persona_manager.format_log(log_type, message)


# Log type constants for easy reference
class LogType:
    """Standard log types for persona theming."""

    PLAN_START = "plan_start"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_MODIFY = "file_modify"
    TEST_START = "test_start"
    TEST_PASS = "test_pass"
    TEST_FAIL = "test_fail"
    ERROR = "error"
    SUCCESS = "success"
    COMMIT = "commit"
    THINKING = "thinking"
