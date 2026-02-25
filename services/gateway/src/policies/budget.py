from __future__ import annotations

import logging
from datetime import date

import redis.asyncio as aioredis
from civicproof_common.config import get_settings

logger = logging.getLogger(__name__)

_COST_PER_1K_TOKENS: dict[str, float] = {
    "vertex": 0.000125,
    "openrouter": 0.000200,
    "vllm": 0.0,
}

_BUDGET_PREFIX = "budget:"
_GLOBAL_DAILY_PREFIX = "budget:daily:"


class BudgetEnforcer:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._settings = get_settings()

    def _case_key(self, case_id: str) -> str:
        return f"{_BUDGET_PREFIX}case:{case_id}:cost_usd"

    def _daily_key(self) -> str:
        today = date.today().isoformat()
        return f"{_GLOBAL_DAILY_PREFIX}{today}"

    def _estimate_cost(self, total_tokens: int, provider: str) -> float:
        rate = _COST_PER_1K_TOKENS.get(provider, 0.0002)
        return (total_tokens / 1000.0) * rate

    async def record_usage(
        self,
        case_id: str | None,
        total_tokens: int,
        provider: str,
    ) -> None:
        cost = self._estimate_cost(total_tokens, provider)
        if case_id:
            await self._redis.incrbyfloat(self._case_key(case_id), cost)
            await self._redis.expire(self._case_key(case_id), 86400 * 7)

        await self._redis.incrbyfloat(self._daily_key(), cost)
        await self._redis.expire(self._daily_key(), 86400 * 2)
        logger.debug("budget_recorded case_id=%s cost=%.6f provider=%s", case_id, cost, provider)

    async def check_case_budget(self, case_id: str) -> tuple[bool, float]:
        raw = await self._redis.get(self._case_key(case_id))
        spent = float(raw) if raw else 0.0
        limit = self._settings.MAX_COST_PER_CASE_USD
        within_budget = spent < limit
        if not within_budget:
            logger.warning(
                "budget_exceeded case_id=%s spent=%.4f limit=%.4f",
                case_id,
                spent,
                limit,
            )
        return within_budget, spent

    async def get_daily_spend(self) -> float:
        raw = await self._redis.get(self._daily_key())
        return float(raw) if raw else 0.0
