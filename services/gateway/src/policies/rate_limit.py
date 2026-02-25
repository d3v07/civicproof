from __future__ import annotations

import logging
import time

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_LLM_RATE_PREFIX = "llm_rate:"


class LLMRateLimiter:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        requests_per_minute: int = 60,
    ) -> None:
        self._redis = redis_client
        self._rpm = requests_per_minute

    def _window_key(self, case_id: str | None) -> str:
        window = int(time.time()) // 60
        scope = case_id or "global"
        return f"{_LLM_RATE_PREFIX}{scope}:{window}"

    async def check_and_increment(self, case_id: str | None = None) -> tuple[bool, int]:
        key = self._window_key(case_id)
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 120)

        allowed = count <= self._rpm
        if not allowed:
            logger.warning(
                "llm_rate_limit_exceeded case_id=%s count=%d limit=%d", case_id, count, self._rpm
            )
        return allowed, count

    async def get_remaining(self, case_id: str | None = None) -> int:
        key = self._window_key(case_id)
        raw = await self._redis.get(key)
        count = int(raw) if raw else 0
        return max(0, self._rpm - count)
