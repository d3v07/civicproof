from __future__ import annotations

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_IDEMPOTENCY_PREFIX = "idempotency:"


class IdempotencyGuard:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def check_and_set(self, key: str, ttl: int = 3600) -> bool:
        full_key = f"{_IDEMPOTENCY_PREFIX}{key}"
        result = await self._redis.set(full_key, "1", ex=ttl, nx=True)
        if result:
            logger.debug("idempotency_key=%s status=new", key)
            return True
        logger.debug("idempotency_key=%s status=duplicate", key)
        return False

    async def release(self, key: str) -> None:
        full_key = f"{_IDEMPOTENCY_PREFIX}{key}"
        await self._redis.delete(full_key)

    async def is_processed(self, key: str) -> bool:
        full_key = f"{_IDEMPOTENCY_PREFIX}{key}"
        return bool(await self._redis.exists(full_key))
