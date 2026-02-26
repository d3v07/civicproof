from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from civicproof_common.config import get_settings

from .providers.openrouter import OpenRouterProvider
from .providers.vertex import VertexAIProvider
from .providers.vllm_local import VLLMLocalProvider
from .providers.gemini_free import GeminiFreeProvider

logger = logging.getLogger(__name__)


class TaskType(StrEnum):
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    HYPOTHESIS = "hypothesis"
    SUMMARIZATION = "summarization"
    ENTITY_EXTRACTION = "entity_extraction"


class ModelRouter:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._vertex = VertexAIProvider()
        self._openrouter = OpenRouterProvider()
        self._vllm = VLLMLocalProvider()
        self._gemini_free = None
        if self._settings.GEMINI_API_KEY:
            self._gemini_free = GeminiFreeProvider()

    def _select_provider(self, task_type: TaskType) -> str:
        if self._settings.GEMINI_API_KEY:
            return "gemini_free"

        if self._settings.DEBUG or not self._settings.GCP_PROJECT_ID:
            if self._settings.OPENROUTER_API_KEY:
                return "openrouter"
            return "vllm"

        if task_type == TaskType.EMBEDDING:
            return "vertex"

        return "vertex"

    async def complete(
        self,
        prompt: str,
        task_type: TaskType = TaskType.COMPLETION,
        system_instruction: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        provider_name = self._select_provider(task_type)
        logger.debug(
            "routing task_type=%s to provider=%s case_id=%s",
            task_type,
            provider_name,
            case_id,
        )

        provider_map = {
            "gemini_free": self._gemini_free,
            "vertex": self._vertex,
            "openrouter": self._openrouter,
            "vllm": self._vllm,
        }

        primary = provider_map[provider_name]
        try:
            return await primary.complete(
                prompt=prompt,
                system_instruction=system_instruction,
                max_tokens=max_tokens,
                temperature=temperature,
                case_id=case_id,
            )
        except Exception as exc:
            logger.warning("primary provider %s failed: %s, trying fallback", provider_name, exc)

        fallback_order = [p for p in ["gemini_free", "openrouter", "vllm", "vertex"] if p != provider_name]
        for fallback_name in fallback_order:
            provider = provider_map[fallback_name]
            try:
                result = await provider.complete(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    case_id=case_id,
                )
                result["fallback_from"] = provider_name
                return result
            except Exception as exc2:
                logger.warning("fallback provider %s also failed: %s", fallback_name, exc2)

        raise RuntimeError(f"All providers failed for task_type={task_type}")

    async def embed(
        self,
        text: str,
        case_id: str | None = None,
    ) -> dict[str, Any]:
        provider_name = self._select_provider(TaskType.EMBEDDING)
        provider_map = {
            "gemini_free": self._gemini_free,
            "vertex": self._vertex,
            "openrouter": self._openrouter,
            "vllm": self._vllm,
        }
        primary = provider_map[provider_name]
        try:
            return await primary.embed(text=text, case_id=case_id)
        except Exception as exc:
            logger.warning("embed provider %s failed: %s", provider_name, exc)

        for fallback_name in ["gemini_free", "openrouter", "vllm", "vertex"]:
            if fallback_name == provider_name:
                continue
            try:
                return await provider_map[fallback_name].embed(text=text, case_id=case_id)
            except Exception as exc2:
                logger.warning("embed fallback %s failed: %s", fallback_name, exc2)

        raise RuntimeError("All embedding providers failed")
