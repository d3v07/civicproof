"""Integration test: API → Redis event → Worker pipeline → DB update.

Verifies the full contract between API case creation, event emission,
worker processing, and database state updates. Uses mocked external
dependencies (LLM, USAspending) but tests real wiring between components.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from civicproof_common.schemas.events import EventEnvelope, EventType  # noqa: E402

# ── Helpers ───────────────────────────────────────────────────────────────

def _build_case_created_event(case_id: str, vendor_name: str) -> str:
    envelope = EventEnvelope.build(
        event_type=EventType.CASE_CREATED,
        source="api",
        payload={"case_id": case_id, "seed_input": {"vendor_name": vendor_name}},
        idempotency_key=f"case_created:{case_id}",
    )
    return envelope.model_dump_json()


def _mock_graph_result(approved: bool = True) -> dict[str, Any]:
    return {
        "case_id": "test-case-id",
        "audit_approved": approved,
        "audit_result": {
            "approved": approved,
            "violations": [] if approved else ["MINIMUM_SOURCES: only 1 source"],
            "summary": "APPROVED" if approved else "BLOCKED",
        },
        "case_pack": {
            "case_id": "test-case-id",
            "title": "Test Case Pack",
            "summary": "Test summary",
            "claims": [
                {
                    "claim_id": "cl-1",
                    "statement": "Entity received $5M in awards.",
                    "claim_type": "finding",
                    "confidence": 1.0,
                    "citation_ids": ["art-001"],
                    "artifact_ids": ["art-001"],
                },
            ],
            "risk_signals": [],
            "entity_profile": {"canonical_name": "TEST CORP"},
            "evidence_summary": {"total_artifacts": 3},
            "timeline": [],
            "sources_used": ["usaspending"],
            "pack_hash": "abc123def456",
        },
        "pipeline_log": [
            {"step": "entity_resolver", "status": "completed"},
            {"step": "evidence_retrieval", "status": "completed"},
            {"step": "case_composer", "status": "completed"},
            {"step": "auditor_gate", "status": "approved"},
        ],
    }


def _mock_async_ctx(mock_db):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ── Event Envelope Contract ──────────────────────────────────────────────

class TestEventEnvelopeContract:
    def test_case_created_event_roundtrip(self):
        case_id = str(uuid.uuid4())
        raw = _build_case_created_event(case_id, "Acme Corp")
        envelope = EventEnvelope.model_validate_json(raw)

        assert envelope.event_type == EventType.CASE_CREATED
        assert envelope.payload["case_id"] == case_id
        assert envelope.payload["seed_input"]["vendor_name"] == "Acme Corp"
        assert envelope.source == "api"

    def test_event_has_idempotency_key(self):
        case_id = str(uuid.uuid4())
        raw = _build_case_created_event(case_id, "Test")
        envelope = EventEnvelope.model_validate_json(raw)
        assert envelope.idempotency_key == f"case_created:{case_id}"

    def test_all_event_types_defined(self):
        expected = {
            "artifact.ingested", "artifact.parse_requested",
            "entity.normalize_requested", "case.created",
        }
        actual = {e.value for e in EventType}
        assert expected.issubset(actual)


# ── Worker Message Processing ────────────────────────────────────────────

class TestWorkerMessageProcessing:
    @pytest.mark.asyncio
    async def test_process_message_dispatches_case_created(self):
        case_id = str(uuid.uuid4())
        raw = _build_case_created_event(case_id, "Test Corp")
        mock_redis = AsyncMock()
        mock_handler = AsyncMock()

        with patch.dict("src.main._HANDLERS", {EventType.CASE_CREATED: mock_handler}):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        assert call_args[0].event_type == EventType.CASE_CREATED
        assert call_args[0].payload["case_id"] == case_id

    @pytest.mark.asyncio
    async def test_process_message_sends_invalid_to_dlq(self):
        mock_redis = AsyncMock()

        from src.main import _process_message
        await _process_message(mock_redis, "not-valid-json{{{")

        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args[0]
        assert call_args[0] == "civicproof:events:dlq"

    @pytest.mark.asyncio
    async def test_process_message_retries_on_handler_error(self):
        case_id = str(uuid.uuid4())
        raw = _build_case_created_event(case_id, "Test")
        mock_redis = AsyncMock()
        mock_handler = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.dict("src.main._HANDLERS", {EventType.CASE_CREATED: mock_handler}):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_redis.rpush.assert_called_once()
        retry_raw = mock_redis.rpush.call_args[0][1]
        retry_envelope = EventEnvelope.model_validate_json(retry_raw)
        assert retry_envelope.payload.get("_retry_count") == 1

    @pytest.mark.asyncio
    async def test_max_retries_sends_to_dlq(self):
        case_id = str(uuid.uuid4())
        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="api",
            payload={"case_id": case_id, "seed_input": {}, "_retry_count": 3},
            idempotency_key=f"case_created:{case_id}:retry:3",
        )
        raw = envelope.model_dump_json()
        mock_redis = AsyncMock()
        mock_handler = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.dict("src.main._HANDLERS", {EventType.CASE_CREATED: mock_handler}):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_redis.lpush.assert_called_once()
        assert mock_redis.rpush.call_count == 0

    @pytest.mark.asyncio
    async def test_unknown_event_type_ignored(self):
        mock_redis = AsyncMock()
        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="api",
            payload={"case_id": "test"},
        )
        raw = envelope.model_dump_json()

        # Clear all handlers so nothing matches
        with patch.dict("src.main._HANDLERS", {}, clear=True):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_redis.lpush.assert_not_called()
        mock_redis.rpush.assert_not_called()


# ── Pipeline Orchestration ───────────────────────────────────────────────

class TestPipelineOrchestration:
    @pytest.mark.asyncio
    async def test_handle_case_created_approved(self):
        case_id = str(uuid.uuid4())
        mock_redis = AsyncMock()

        mock_case = MagicMock()
        mock_case.status = "pending"
        mock_case.updated_at = datetime.now(UTC)

        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_case
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        graph_result = _mock_graph_result(approved=True)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="api",
            payload={"case_id": case_id, "seed_input": {"vendor_name": "Test Corp"}},
        )

        with (
            patch("src.main.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.main.get_compiled_graph", return_value=mock_graph),
            patch("src.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.LANGGRAPH_RECURSION_LIMIT = 25
            from src.main import handle_case_created
            await handle_case_created(envelope, mock_redis)

        mock_graph.ainvoke.assert_called_once()
        invoke_args = mock_graph.ainvoke.call_args
        assert invoke_args[0][0]["case_id"] == case_id
        assert invoke_args[0][0]["seed_input"]["vendor_name"] == "Test Corp"

        # Status was updated to "complete"
        assert mock_case.status == "complete"

    @pytest.mark.asyncio
    async def test_handle_case_created_blocked(self):
        case_id = str(uuid.uuid4())
        mock_redis = AsyncMock()

        mock_case = MagicMock()
        mock_case.status = "pending"

        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_case
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        graph_result = _mock_graph_result(approved=False)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=graph_result)

        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="api",
            payload={"case_id": case_id, "seed_input": {"vendor_name": "Blocked Corp"}},
        )

        with (
            patch("src.main.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.main.get_compiled_graph", return_value=mock_graph),
            patch("src.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.LANGGRAPH_RECURSION_LIMIT = 25
            from src.main import handle_case_created
            await handle_case_created(envelope, mock_redis)

        assert mock_case.status == "insufficient_evidence"

    @pytest.mark.asyncio
    async def test_handle_case_created_pipeline_failure(self):
        case_id = str(uuid.uuid4())
        mock_redis = AsyncMock()

        mock_case = MagicMock()
        mock_case.status = "pending"

        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_case
        mock_db.execute = AsyncMock(return_value=mock_execute_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("pipeline crash"))

        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="api",
            payload={"case_id": case_id, "seed_input": {"vendor_name": "Crash Corp"}},
        )

        with (
            patch("src.main.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.main.get_compiled_graph", return_value=mock_graph),
            patch("src.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.LANGGRAPH_RECURSION_LIMIT = 25
            from src.main import handle_case_created
            await handle_case_created(envelope, mock_redis)

        assert mock_case.status == "failed"


# ── Save Case Pack Contract ──────────────────────────────────────────────

class TestSaveCasePack:
    @pytest.mark.asyncio
    async def test_save_case_pack_creates_claims_and_citations(self):
        mock_db = AsyncMock()
        added_models = []
        mock_db.add = MagicMock(side_effect=lambda m: added_models.append(m))
        mock_db.commit = AsyncMock()

        result = _mock_graph_result(approved=True)

        from src.main import _save_case_pack
        await _save_case_pack(mock_db, "test-case-id", result)

        mock_db.commit.assert_called_once()
        # 1 ClaimModel + 1 CitationModel (for "art-001") + 1 CasePackModel = 3
        assert len(added_models) == 3

    @pytest.mark.asyncio
    async def test_save_case_pack_empty_claims(self):
        mock_db = AsyncMock()
        added_models = []
        mock_db.add = MagicMock(side_effect=lambda m: added_models.append(m))
        mock_db.commit = AsyncMock()

        result = {"case_pack": {"claims": [], "pack_hash": "empty"}}

        from src.main import _save_case_pack
        await _save_case_pack(mock_db, "test-case-id", result)

        # Only CasePackModel
        assert len(added_models) == 1


# ── Handler Registry ─────────────────────────────────────────────────────

class TestHandlerRegistry:
    def test_all_event_types_have_handlers(self):
        from src.main import _HANDLERS

        assert EventType.CASE_CREATED in _HANDLERS
        assert EventType.ARTIFACT_INGESTED in _HANDLERS
        assert EventType.ARTIFACT_PARSE_REQUESTED in _HANDLERS
        assert EventType.ENTITY_NORMALIZE_REQUESTED in _HANDLERS

    def test_handlers_are_callable(self):
        from src.main import _HANDLERS

        for event_type, handler in _HANDLERS.items():
            assert callable(handler), f"Handler for {event_type} is not callable"
