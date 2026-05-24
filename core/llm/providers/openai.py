"""OpenAI LLM provider implementation."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator
import httpx

from ..provider import LLMProvider, LLMMessage, LLMResponse, LLMProviderFactory


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider (GPT-4, GPT-3.5, etc.)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4-turbo-preview",
        base_url: str = "https://api.openai.com/v1",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    @property
    def name(self) -> str:
        return "openai"

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
        """Generate completion using OpenAI API."""
        if not self.is_configured():
            raise ValueError("OpenAI API key not configured")

        # Convert messages to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Build request
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Make request
        response = await self._client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        response.raise_for_status()

        data = response.json()

        # Extract content
        content = data["choices"][0]["message"]["content"]

        return LLMResponse(
            content=content,
            model=data["model"],
            usage=data.get("usage"),
            finish_reason=data["choices"][0].get("finish_reason")
        )

    async def stream_generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream completion using OpenAI API."""
        if not self.is_configured():
            raise ValueError("OpenAI API key not configured")

        # Convert messages
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Build request
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        # Stream request
        async with self._client.stream(
            "POST",
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        import json
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"]
                        if "content" in delta:
                            yield delta["content"]
                    except:
                        continue

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()


# Register provider
LLMProviderFactory.register("openai", OpenAIProvider)
