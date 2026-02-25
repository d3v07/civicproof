from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "llm_cache:"
_DEFAULT_TTL = 3600 * 24


class SemanticCache:
    def __init__(self, redis_client: aioredis.Redis, ttl: int = _DEFAULT_TTL) -> None:
        self._redis = redis_client
        self._ttl = ttl

    def _cache_key(self, prompt: str, model: str, system_instruction: str | None) -> str:
        payload = json.dumps(
            {"prompt": prompt, "model": model, "system": system_instruction or ""},
            sort_keys=True,
        )
        hash_value = hashlib.sha256(payload.encode()).hexdigest()
        return f"{_CACHE_PREFIX}{hash_value}"

    async def get(
        self,
        prompt: str,
        model: str,
        system_instruction: str | None = None,
    ) -> dict[str, Any] | None:
        key = self._cache_key(prompt, model, system_instruction)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("corrupt cache entry for key=%s", key)
            await self._redis.delete(key)
            return None

    async def set(
        self,
        prompt: str,
        model: str,
        result: dict[str, Any],
        system_instruction: str | None = None,
    ) -> None:
        key = self._cache_key(prompt, model, system_instruction)
        await self._redis.set(key, json.dumps(result), ex=self._ttl)

    async def invalidate(
        self,
        prompt: str,
        model: str,
        system_instruction: str | None = None,
    ) -> None:
        key = self._cache_key(prompt, model, system_instruction)
        await self._redis.delete(key)
