from __future__ import annotations

import logging
from typing import Any

from civicproof_common.config import get_settings
from google import genai

logger = logging.getLogger(__name__)

class GeminiFreeProvider:
    """Provider for the free-tier Gemini API using the official google-genai SDK."""

    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
            
        self.model = self._settings.VERTEX_AI_MODEL
        self.client = genai.Client(api_key=self._settings.GEMINI_API_KEY)

    async def complete(
        self,
        prompt: str,
        system_instruction: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        case_id: str | None = None,
    ) -> dict[str, Any]:
    
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        # Run synchronously inside an async wrapper since the SDK handles threading
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )

        text = response.text or ""
        
        usage = {}
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }

        return {
            "text": text,
            "usage": usage,
            "provider": "gemini_free",
            "model": self.model,
        }

    async def embed(self, text: str, case_id: str | None = None) -> dict[str, Any]:
        result = self.client.models.embed_content(
            model="text-embedding-004",
            contents=text[:8000],
        )
        
        # result.embeddings is a list of Embedding objects. Get the first one's values.
        embedding_values = []
        if result.embeddings and len(result.embeddings) > 0:
            embedding_values = result.embeddings[0].values
            
        return {
            "embedding": embedding_values,
            "provider": "gemini_free",
            "model": "text-embedding-004"
        }
