"""Unit tests for worker handler functions (ingest, parse, normalize).

Tests async handlers with mocked DB, Redis, object store, idempotency guard.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from civicproof_common.schemas.events import EventEnvelope, EventType


def _make_envelope(event_type: EventType, payload: dict, **kwargs) -> EventEnvelope:
    return EventEnvelope.build(
        event_type=event_type,
        source="test",
        payload=payload,
        **kwargs,
    )


def _mock_db_session():
    """Create a mock async generator yielding a mock DB session."""
    mock_db = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_execute_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    return mock_db


async def _mock_get_session(mock_db):
    yield mock_db


# ── Ingest Handler ───────────────────────────────────────────────────────

class TestHandleArtifactIngested:
    @pytest.mark.asyncio
    async def test_stores_artifact_and_emits_parse_event(self):
        mock_redis = AsyncMock()
        mock_db = _mock_db_session()
        mock_store = AsyncMock()
        mock_store.storage_key = MagicMock(return_value="artifacts/test/hash123")
        mock_store.artifact_exists = AsyncMock(return_value=False)
        mock_store.put_artifact = AsyncMock()

        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_INGESTED,
            {
                "artifact_id": "art-001",
                "source": "usaspending",
                "source_url": "https://api.usaspending.gov/test",
                "raw_data_hex": b"hello world".hex(),
                "doc_type": "contract_award",
            },
        )

        with (
            patch("src.handlers.ingest.get_session", side_effect=lambda: _mock_get_session(mock_db)),
            patch("src.handlers.ingest.build_object_store", return_value=mock_store),
            patch("src.handlers.ingest.IdempotencyGuard", return_value=mock_guard),
            patch("src.handlers.ingest.content_hash", return_value="hash123"),
            patch("src.handlers.ingest.verify_hash", return_value=True),
        ):
            from src.handlers.ingest import handle_artifact_ingested
            await handle_artifact_ingested(envelope, mock_redis)

        mock_store.put_artifact.assert_called_once()
        mock_db.add.assert_called_once()
        mock_redis.rpush.assert_called_once()
        # Verify parse event was emitted
        parse_event_raw = mock_redis.rpush.call_args[0][1]
        parse_event = EventEnvelope.model_validate_json(parse_event_raw)
        assert parse_event.event_type == EventType.ARTIFACT_PARSE_REQUESTED
        assert parse_event.payload["artifact_id"] == "art-001"

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_skipped(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=False)

        envelope = _make_envelope(
            EventType.ARTIFACT_INGESTED,
            {"artifact_id": "art-001", "source": "test", "raw_data_hex": "aabb"},
        )

        with patch("src.handlers.ingest.IdempotencyGuard", return_value=mock_guard):
            from src.handlers.ingest import handle_artifact_ingested
            await handle_artifact_ingested(envelope, mock_redis)

        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_raw_data_hex_returns_early(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_INGESTED,
            {"artifact_id": "art-001", "source": "test", "raw_data_hex": ""},
        )

        with patch("src.handlers.ingest.IdempotencyGuard", return_value=mock_guard):
            from src.handlers.ingest import handle_artifact_ingested
            await handle_artifact_ingested(envelope, mock_redis)

        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_hash_mismatch_returns_early(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_INGESTED,
            {
                "artifact_id": "art-001",
                "source": "test",
                "raw_data_hex": b"data".hex(),
                "content_hash": "wrong_hash",
            },
        )

        with (
            patch("src.handlers.ingest.IdempotencyGuard", return_value=mock_guard),
            patch("src.handlers.ingest.content_hash", return_value="correct_hash"),
            patch("src.handlers.ingest.verify_hash", return_value=False),
        ):
            from src.handlers.ingest import handle_artifact_ingested
            await handle_artifact_ingested(envelope, mock_redis)

        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_artifact_in_store_not_reuploaded(self):
        mock_redis = AsyncMock()
        mock_db = _mock_db_session()
        mock_store = AsyncMock()
        mock_store.storage_key = MagicMock(return_value="artifacts/test/hash123")
        mock_store.artifact_exists = AsyncMock(return_value=True)

        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_INGESTED,
            {"artifact_id": "art-001", "source": "test", "raw_data_hex": b"data".hex()},
        )

        with (
            patch("src.handlers.ingest.get_session", side_effect=lambda: _mock_get_session(mock_db)),
            patch("src.handlers.ingest.build_object_store", return_value=mock_store),
            patch("src.handlers.ingest.IdempotencyGuard", return_value=mock_guard),
            patch("src.handlers.ingest.content_hash", return_value="hash123"),
        ):
            from src.handlers.ingest import handle_artifact_ingested
            await handle_artifact_ingested(envelope, mock_redis)

        mock_store.put_artifact.assert_not_called()


# ── Parse Handler ────────────────────────────────────────────────────────

class TestHandleParseRequested:
    @pytest.mark.asyncio
    async def test_parses_and_emits_normalize_event(self):
        mock_redis = AsyncMock()
        mock_db = _mock_db_session()
        mock_store = AsyncMock()
        data = json.dumps({"vendor_name": "Acme"}).encode()
        mock_store.get_artifact = AsyncMock(return_value=data)

        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_PARSE_REQUESTED,
            {
                "artifact_id": "art-001",
                "source": "usaspending",
                "storage_path": "artifacts/usa/hash123",
                "doc_type": "contract_award",
            },
        )

        with (
            patch("src.handlers.parse.get_session", side_effect=lambda: _mock_get_session(mock_db)),
            patch("src.handlers.parse.build_object_store", return_value=mock_store),
            patch("src.handlers.parse.IdempotencyGuard", return_value=mock_guard),
        ):
            from src.handlers.parse import handle_parse_requested
            await handle_parse_requested(envelope, mock_redis)

        mock_db.add.assert_called_once()
        mock_redis.rpush.assert_called_once()
        norm_event = EventEnvelope.model_validate_json(mock_redis.rpush.call_args[0][1])
        assert norm_event.event_type == EventType.ENTITY_NORMALIZE_REQUESTED
        assert norm_event.payload["artifact_id"] == "art-001"

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_skipped(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=False)

        envelope = _make_envelope(
            EventType.ARTIFACT_PARSE_REQUESTED,
            {"artifact_id": "art-001", "source": "test", "storage_path": "x", "doc_type": "unknown"},
        )

        with patch("src.handlers.parse.IdempotencyGuard", return_value=mock_guard):
            from src.handlers.parse import handle_parse_requested
            await handle_parse_requested(envelope, mock_redis)

        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_artifact_id_returns_early(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_PARSE_REQUESTED,
            {"artifact_id": "", "source": "test", "storage_path": "", "doc_type": "unknown"},
        )

        with patch("src.handlers.parse.IdempotencyGuard", return_value=mock_guard):
            from src.handlers.parse import handle_parse_requested
            await handle_parse_requested(envelope, mock_redis)

        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_object_store_failure_returns_early(self):
        mock_redis = AsyncMock()
        mock_store = AsyncMock()
        mock_store.get_artifact = AsyncMock(side_effect=RuntimeError("store down"))

        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ARTIFACT_PARSE_REQUESTED,
            {"artifact_id": "art-001", "source": "test", "storage_path": "x/y", "doc_type": "unknown"},
        )

        with (
            patch("src.handlers.parse.build_object_store", return_value=mock_store),
            patch("src.handlers.parse.IdempotencyGuard", return_value=mock_guard),
        ):
            from src.handlers.parse import handle_parse_requested
            await handle_parse_requested(envelope, mock_redis)

        mock_redis.rpush.assert_not_called()


# ── Normalize Handler ────────────────────────────────────────────────────

class TestHandleNormalizeRequested:
    @pytest.mark.asyncio
    async def test_creates_entity_and_mention(self):
        mock_redis = AsyncMock()
        mock_db = _mock_db_session()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ENTITY_NORMALIZE_REQUESTED,
            {
                "artifact_id": "art-001",
                "source": "usaspending",
                "text_snippet": "UEI ABC123DEF456",
                "structured_data": {"vendor_name": "Acme Corp"},
            },
        )

        with (
            patch("src.handlers.normalize.get_session", side_effect=lambda: _mock_get_session(mock_db)),
            patch("src.handlers.normalize.IdempotencyGuard", return_value=mock_guard),
        ):
            from src.handlers.normalize import handle_normalize_requested
            await handle_normalize_requested(envelope, mock_redis)

        # EntityModel + EntityMentionModel = 2 adds
        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_skipped(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=False)

        envelope = _make_envelope(
            EventType.ENTITY_NORMALIZE_REQUESTED,
            {"artifact_id": "art-001", "source": "test", "text_snippet": "", "structured_data": {}},
        )

        with patch("src.handlers.normalize.IdempotencyGuard", return_value=mock_guard):
            from src.handlers.normalize import handle_normalize_requested
            await handle_normalize_requested(envelope, mock_redis)

    @pytest.mark.asyncio
    async def test_existing_entity_updates_alias(self):
        mock_redis = AsyncMock()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        existing_entity = MagicMock()
        existing_entity.entity_id = "ent-existing"
        existing_entity.canonical_name = "ACME CORP"
        existing_entity.aliases = []
        existing_entity.uei = None
        existing_entity.cage_code = None

        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = existing_entity
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        envelope = _make_envelope(
            EventType.ENTITY_NORMALIZE_REQUESTED,
            {
                "artifact_id": "art-001",
                "source": "usaspending",
                "text_snippet": "",
                "structured_data": {"vendor_name": "Acme Corp", "uei": "ABC123DEF456"},
            },
        )

        with (
            patch("src.handlers.normalize.get_session", side_effect=lambda: _mock_get_session(mock_db)),
            patch("src.handlers.normalize.IdempotencyGuard", return_value=mock_guard),
        ):
            from src.handlers.normalize import handle_normalize_requested
            await handle_normalize_requested(envelope, mock_redis)

        # Entity should get alias and UEI updated
        assert "Acme Corp" in existing_entity.aliases
        assert existing_entity.uei == "ABC123DEF456"

    @pytest.mark.asyncio
    async def test_empty_vendor_names_no_entities_created(self):
        mock_redis = AsyncMock()
        mock_db = _mock_db_session()
        mock_guard = AsyncMock()
        mock_guard.check_and_set = AsyncMock(return_value=True)

        envelope = _make_envelope(
            EventType.ENTITY_NORMALIZE_REQUESTED,
            {
                "artifact_id": "art-001",
                "source": "test",
                "text_snippet": "no identifiers",
                "structured_data": {},
            },
        )

        with (
            patch("src.handlers.normalize.get_session", side_effect=lambda: _mock_get_session(mock_db)),
            patch("src.handlers.normalize.IdempotencyGuard", return_value=mock_guard),
        ):
            from src.handlers.normalize import handle_normalize_requested
            await handle_normalize_requested(envelope, mock_redis)

        mock_db.add.assert_not_called()
