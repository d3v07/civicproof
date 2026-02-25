from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_RATE_LIMIT_PREFIX = "ratelimit:"


@dataclass(frozen=True)
class SourceLimit:
    tokens_per_second: float
    burst: int


SOURCE_LIMITS: dict[str, SourceLimit] = {
    "sec_edgar": SourceLimit(tokens_per_second=10.0, burst=10),
    "doj": SourceLimit(tokens_per_second=4.0, burst=4),
    "sam_gov": SourceLimit(tokens_per_second=4.0, burst=4),
    "openfec": SourceLimit(tokens_per_second=1000 / 3600, burst=10),
    "usaspending": SourceLimit(tokens_per_second=5.0, burst=5),
    "oversight_gov": SourceLimit(tokens_per_second=2.0, burst=2),
}

_DEFAULT_LIMIT = SourceLimit(tokens_per_second=1.0, burst=1)

_LUA_ACQUIRE = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local burst = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = burst
    last_refill = now
end

local elapsed = now - last_refill
local added = elapsed * refill_rate
tokens = math.min(burst, tokens + added)
last_refill = now

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', key, 3600)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
    redis.call('EXPIRE', key, 3600)
    return 0
end
"""


class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._script = self._redis.register_script(_LUA_ACQUIRE)

    def _get_limit(self, source: str) -> SourceLimit:
        return SOURCE_LIMITS.get(source, _DEFAULT_LIMIT)

    async def acquire(self, source: str) -> bool:
        limit = self._get_limit(source)
        key = f"{_RATE_LIMIT_PREFIX}{source}"
        now = time.monotonic()
        result = await self._script(
            keys=[key],
            args=[1, now, limit.tokens_per_second, limit.burst],
        )
        acquired = bool(result)
        logger.debug("rate_limit source=%s acquired=%s", source, acquired)
        return acquired

    async def wait_for_token(self, source: str) -> None:
        limit = self._get_limit(source)
        wait_seconds = 1.0 / limit.tokens_per_second
        while True:
            if await self.acquire(source):
                return
            await asyncio.sleep(min(wait_seconds, 1.0))
