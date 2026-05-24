"""Gemini LLM provider implementation."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator
import httpx

from .provider import LLMProvider, LLMMessage, LLMResponse, LLMProviderFactory


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash-exp",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._model = model
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

    @property
    def name(self) -> str:
        return "gemini"

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
        """Generate completion using Gemini API."""
        if not self.is_configured():
            raise ValueError("Gemini API key not configured")

        # Convert messages to Gemini format
        contents = []
        system_instruction = None

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            else:
                contents.append({
                    "role": "user" if msg.role == "user" else "model",
                    "parts": [{"text": msg.content}]
                })

        # Build request
        url = f"{self.base_url}/models/{self._model}:generateContent"
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Make request
        response = await self._client.post(
            url,
            params={"key": self.api_key},
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()

        data = response.json()

        # Extract content
        content = ""
        if "candidates" in data and data["candidates"]:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                content = candidate["content"]["parts"][0].get("text", "")

        return LLMResponse(
            content=content,
            model=self._model,
            usage=data.get("usageMetadata"),
            finish_reason=data.get("candidates", [{}])[0].get("finishReason")
        )

    async def stream_generate(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream completion using Gemini API."""
        # For now, fallback to non-streaming
        response = await self.generate(messages, temperature, max_tokens, **kwargs)
        yield response.content

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()


# Register provider
LLMProviderFactory.register("gemini", GeminiProvider)
