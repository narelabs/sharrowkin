"""LLM Provider abstraction for supporting multiple LLM backends.

Supports: Gemini, OpenAI, Anthropic, local models via llama.cpp.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from dataclasses import dataclass


@dataclass
class LLMMessage:
    """Single message in conversation."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    model: str
    usage: dict[str, int] | None = None  # tokens used
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> LLMResponse:
        """Generate completion from messages.

        Args:
            messages: Conversation history
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    async def stream_generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream completion from messages.

        Args:
            messages: Conversation history
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Yields:
            Content chunks as they arrive
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """Model identifier."""
        pass


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    _providers: dict[str, type[LLMProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[LLMProvider]) -> None:
        """Register a provider class.

        Args:
            name: Provider name (e.g., "gemini", "openai")
            provider_class: Provider class to register
        """
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> LLMProvider:
        """Create provider instance.

        Args:
            name: Provider name
            **kwargs: Provider-specific configuration

        Returns:
            Configured LLMProvider instance

        Raises:
            ValueError: If provider not registered
        """
        if name not in cls._providers:
            raise ValueError(
                f"Unknown provider: {name}. "
                f"Available: {', '.join(cls._providers.keys())}"
            )

        return cls._providers[name](**kwargs)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List registered provider names."""
        return list(cls._providers.keys())
