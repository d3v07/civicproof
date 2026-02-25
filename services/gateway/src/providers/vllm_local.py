from __future__ import annotations

import logging
from typing import Any

import httpx
from civicproof_common.config import get_settings

logger = logging.getLogger(__name__)


class VLLMLocalProvider:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def complete(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._settings.VLLM_BASE_URL}/chat/completions",
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
            "provider": "vllm_local",
            "model": self._settings.VLLM_MODEL,
        }

    async def embed(self, text: str, case_id: str | None = None) -> dict[str, Any]:
        body = {
            "model": self._settings.VLLM_MODEL,
            "input": text[:8000],
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._settings.VLLM_BASE_URL}/embeddings",
                json=body,
            )
            response.raise_for_status()
            data = response.json()

        embedding = data.get("data", [{}])[0].get("embedding", [])
        return {
            "embedding": embedding,
            "provider": "vllm_local",
            "model": self._settings.VLLM_MODEL,
        }
