from __future__ import annotations

import logging
from typing import Any

import httpx
from civicproof_common.config import get_settings

logger = logging.getLogger(__name__)

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://civicproof.ai",
            "X-Title": "CivicProof",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._settings.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._settings.OPENROUTER_DEFAULT_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OPENROUTER_API_BASE}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        choice = data.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})

        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "provider": "openrouter",
            "model": self._settings.OPENROUTER_DEFAULT_MODEL,
        }

    async def embed(self, text: str, case_id: str | None = None) -> dict[str, Any]:
        if not self._settings.OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        body = {
            "model": "openai/text-embedding-3-small",
            "input": text[:8000],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OPENROUTER_API_BASE}/embeddings",
                headers=self._headers(),
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        embedding = data.get("data", [{}])[0].get("embedding", [])
        return {"embedding": embedding, "provider": "openrouter", "model": "text-embedding-3-small"}
