"""Core LLM integrations for Sharrowkin Agent.

Unified LLM client supporting multiple providers:
- Gemini (Google)
- Claude (Anthropic)
- GPT (OpenAI)
"""

from .client import GeminiClient, AUTONOMOUS_AGENT_POLICY, GeneratedPatch

__all__ = [
    "GeminiClient",
    "AUTONOMOUS_AGENT_POLICY",
    "GeneratedPatch",
]
