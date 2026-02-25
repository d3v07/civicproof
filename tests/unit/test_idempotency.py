from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from civicproof_common.idempotency import IdempotencyGuard


class TestIdempotencyGuard:
    @pytest.mark.asyncio
    async def test_new_key_returns_true(self, mock_redis):
        mock_redis.set = AsyncMock(return_value=True)
        guard = IdempotencyGuard(mock_redis)
        result = await guard.check_and_set("test-key-001")
        assert result is True
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_key_returns_false(self, mock_redis):
        mock_redis.set = AsyncMock(return_value=None)
        guard = IdempotencyGuard(mock_redis)
        result = await guard.check_and_set("test-key-001")
        assert result is False

    @pytest.mark.asyncio
    async def test_check_and_set_uses_correct_prefix(self, mock_redis):
        mock_redis.set = AsyncMock(return_value=True)
        guard = IdempotencyGuard(mock_redis)
        await guard.check_and_set("my-event-key")
        call_args = mock_redis.set.call_args
        key_arg = call_args[0][0]
        assert key_arg == "idempotency:my-event-key"

    @pytest.mark.asyncio
    async def test_ttl_is_passed_to_redis(self, mock_redis):
        mock_redis.set = AsyncMock(return_value=True)
        guard = IdempotencyGuard(mock_redis)
        await guard.check_and_set("key", ttl=7200)
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs.get("ex") == 7200

    @pytest.mark.asyncio
    async def test_default_ttl_is_3600(self, mock_redis):
        mock_redis.set = AsyncMock(return_value=True)
        guard = IdempotencyGuard(mock_redis)
        await guard.check_and_set("key")
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_nx_flag_is_set(self, mock_redis):
        mock_redis.set = AsyncMock(return_value=True)
        guard = IdempotencyGuard(mock_redis)
        await guard.check_and_set("key")
        call_kwargs = mock_redis.set.call_args[1]
        assert call_kwargs.get("nx") is True

    @pytest.mark.asyncio
    async def test_release_deletes_key(self, mock_redis):
        mock_redis.delete = AsyncMock(return_value=1)
        guard = IdempotencyGuard(mock_redis)
        await guard.release("my-key")
        mock_redis.delete.assert_called_once_with("idempotency:my-key")

    @pytest.mark.asyncio
    async def test_is_processed_returns_true_when_exists(self, mock_redis):
        mock_redis.exists = AsyncMock(return_value=1)
        guard = IdempotencyGuard(mock_redis)
        result = await guard.is_processed("existing-key")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_processed_returns_false_when_absent(self, mock_redis):
        mock_redis.exists = AsyncMock(return_value=0)
        guard = IdempotencyGuard(mock_redis)
        result = await guard.is_processed("missing-key")
        assert result is False

    @pytest.mark.asyncio
    async def test_first_call_new_second_call_duplicate(self, mock_redis):
        call_count = 0

        async def mock_set(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return True if call_count == 1 else None

        mock_redis.set = mock_set
        guard = IdempotencyGuard(mock_redis)

        result1 = await guard.check_and_set("idempotent-key")
        result2 = await guard.check_and_set("idempotent-key")

        assert result1 is True
        assert result2 is False
