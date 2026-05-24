"""Anthropic Claude LLM provider implementation."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator
import httpx

from ..provider import LLMProvider, LLMMessage, LLMResponse, LLMProviderFactory


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        base_url: str = "https://api.anthropic.com/v1",
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._model = model
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> LLMResponse:
        """Generate completion using Anthropic API."""
        if not self.is_configured():
            raise ValueError("Anthropic API key not configured")

        # Separate system message from conversation
        system_message = None
        conversation = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                conversation.append({
                    "role": msg.role,
                    "content": msg.content
                })

        # Build request
        url = f"{self.base_url}/messages"
        payload = {
            "model": self._model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_message:
            payload["system"] = system_message

        # Make request
        response = await self._client.post(
            url,
            json=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        )
        response.raise_for_status()

        data = response.json()

        # Extract content
        content = ""
        if "content" in data and data["content"]:
            content = data["content"][0].get("text", "")

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            usage=data.get("usage"),
            finish_reason=data.get("stop_reason")
        )

    async def stream_generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream completion using Anthropic API."""
        if not self.is_configured():
            raise ValueError("Anthropic API key not configured")

        # Separate system message
        system_message = None
        conversation = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                conversation.append({
                    "role": msg.role,
                    "content": msg.content
                })

        # Build request
        url = f"{self.base_url}/messages"
        payload = {
            "model": self._model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        if system_message:
            payload["system"] = system_message

        # Stream request
        async with self._client.stream(
            "POST",
            url,
            json=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        import json
                        data = json.loads(data_str)
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if "text" in delta:
                                yield delta["text"]
                    except:
                        continue

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()


# Register provider
LLMProviderFactory.register("anthropic", AnthropicProvider)
