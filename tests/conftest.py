from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from civicproof_common.schemas.events import EventEnvelope, EventType


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.incrbyfloat = AsyncMock(return_value=0.001)
    redis.ping = AsyncMock(return_value=True)
    redis.blpop = AsyncMock(return_value=None)
    redis.rpush = AsyncMock(return_value=1)
    redis.lpush = AsyncMock(return_value=1)
    redis.register_script = MagicMock(return_value=AsyncMock(return_value=1))
    return redis


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def test_artifact_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def test_case_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def make_event_envelope():
    def _factory(
        event_type: EventType = EventType.ARTIFACT_INGESTED,
        source: str = "test",
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope.build(
            event_type=event_type,
            source=source,
            payload=payload or {"test": True},
            idempotency_key=idempotency_key or str(uuid.uuid4()),
        )

    return _factory


@pytest.fixture
def sample_raw_bytes() -> bytes:
    return b'{"vendor_name": "Apex Solutions LLC", "uei": "ABCDEF123456", "amount": 500000}'


@pytest.fixture
def sample_artifact_payload(test_artifact_id, sample_raw_bytes) -> dict[str, Any]:
    from civicproof_common.hashing import content_hash

    raw_hex = sample_raw_bytes.hex()
    return {
        "artifact_id": test_artifact_id,
        "source": "usaspending",
        "source_url": "https://api.usaspending.gov/awards/test-123",
        "raw_data_hex": raw_hex,
        "content_hash": content_hash(sample_raw_bytes),
        "doc_type": "contract_award",
        "metadata": {"fiscal_year": "2024"},
    }
