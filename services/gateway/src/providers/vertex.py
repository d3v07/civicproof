from __future__ import annotations

import logging
from typing import Any

import httpx
from civicproof_common.config import get_settings

logger = logging.getLogger(__name__)

_VERTEX_COMPLETION_URL = (
    "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/"
    "{location}/publishers/google/models/{model}:generateContent"
)


class VertexAIProvider:
    def __init__(self) -> None:
        self._settings = get_settings()

    def _get_url(self) -> str:
        return _VERTEX_COMPLETION_URL.format(
            location=self._settings.VERTEX_AI_LOCATION,
            project=self._settings.GCP_PROJECT_ID or "local",
            model=self._settings.VERTEX_AI_MODEL,
        )

    async def complete(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self._get_url(), json=body)
            response.raise_for_status()
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return {"text": "", "usage": {}, "provider": "vertex"}

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        text = "".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})
        return {
            "text": text,
            "usage": {
                "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                "total_tokens": usage_meta.get("totalTokenCount", 0),
            },
            "provider": "vertex",
            "model": self._settings.VERTEX_AI_MODEL,
        }

    async def embed(self, text: str, case_id: str | None = None) -> dict[str, Any]:
        embed_url = (
            "https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/"
            "{location}/publishers/google/models/text-embedding-004:predict"
        ).format(
            location=self._settings.VERTEX_AI_LOCATION,
            project=self._settings.GCP_PROJECT_ID or "local",
        )
        body = {"instances": [{"content": text[:8000]}]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(embed_url, json=body)
            response.raise_for_status()
            data = response.json()

        predictions = data.get("predictions", [])
        embedding = predictions[0].get("embeddings", {}).get("values", []) if predictions else []
        return {"embedding": embedding, "provider": "vertex", "model": "text-embedding-004"}
