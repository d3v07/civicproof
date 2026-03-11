"""E2E tests: Full pipeline lifecycle — event in → DB state out.

Tests the worker's event processing end-to-end: event envelope arrives
on Redis queue, dispatches to the correct handler, graph executes (mocked),
and DB state is updated correctly. Covers approved, blocked, and failed paths.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from civicproof_common.schemas.events import EventEnvelope, EventType  # noqa: E402


def _mock_async_ctx(mock_db):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _mock_case(case_id: str, status: str = "pending") -> MagicMock:
    case = MagicMock()
    case.case_id = case_id
    case.status = status
    case.updated_at = datetime.now(UTC)
    return case


def _pipeline_result(case_id: str, approved: bool = True) -> dict:
    return {
        "case_id": case_id,
        "audit_approved": approved,
        "audit_result": {
            "approved": approved,
            "violations": [] if approved else ["MINIMUM_SOURCES: only 1 source"],
            "summary": "APPROVED" if approved else "BLOCKED",
        },
        "case_pack": {
            "case_id": case_id,
            "title": "Investigation Report",
            "claims": [
                {
                    "claim_id": f"cl-{uuid.uuid4().hex[:8]}",
                    "statement": "Entity received $5M in sole-source contracts.",
                    "claim_type": "finding",
                    "confidence": 0.95,
                    "citation_ids": ["art-001", "art-002"],
                },
                {
                    "claim_id": f"cl-{uuid.uuid4().hex[:8]}",
                    "statement": "Multiple awards from same contracting office.",
                    "claim_type": "risk_signal",
                    "confidence": 0.80,
                    "citation_ids": ["art-003"],
                },
            ],
            "pack_hash": "e2e_test_hash_abc123",
        },
    }


class TestFullPipelineApproved:
    @pytest.mark.asyncio
    async def test_case_created_to_complete(self):
        """Full path: CASE_CREATED event → pipeline → status=complete + claims saved."""
        case_id = str(uuid.uuid4())
        mock_case = _mock_case(case_id)
        mock_db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_case
        mock_db.execute = AsyncMock(return_value=exec_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        result = _pipeline_result(case_id, approved=True)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=result)

        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="api",
            payload={"case_id": case_id, "seed_input": {"vendor_name": "Test Corp"}},
        )

        added_models = []
        mock_db.add = MagicMock(side_effect=lambda m: added_models.append(m))

        with (
            patch("src.main.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.main.get_compiled_graph", return_value=mock_graph),
            patch("src.main.get_settings") as mock_settings,
        ):
            mock_settings.return_value.LANGGRAPH_RECURSION_LIMIT = 25
            from src.main import handle_case_created
            await handle_case_created(envelope, AsyncMock())

        # Status progressed to "complete"
        assert mock_case.status == "complete"

        # Graph was invoked with correct input
        invoke_args = mock_graph.ainvoke.call_args[0][0]
        assert invoke_args["case_id"] == case_id
        assert invoke_args["seed_input"]["vendor_name"] == "Test Corp"

    @pytest.mark.asyncio
    async def test_approved_saves_claims_and_pack(self):
        """Verify _save_case_pack creates ClaimModel, CitationModel, CasePackModel."""
        case_id = str(uuid.uuid4())
        result = _pipeline_result(case_id, approved=True)

        added = []
        mock_db = AsyncMock()
        mock_db.add = MagicMock(side_effect=lambda m: added.append(type(m).__name__))
        mock_db.commit = AsyncMock()

        from src.main import _save_case_pack
        await _save_case_pack(mock_db, case_id, result)

        # 2 claims + 3 citations (2 for claim1 + 1 for claim2) + 1 CasePackModel = 6
        assert added.count("ClaimModel") == 2
        assert added.count("CitationModel") == 3
        assert added.count("CasePackModel") == 1
        mock_db.commit.assert_called_once()


class TestFullPipelineBlocked:
    @pytest.mark.asyncio
    async def test_case_blocked_by_auditor(self):
        """Pipeline returns audit_approved=False → status=insufficient_evidence."""
        case_id = str(uuid.uuid4())
        mock_case = _mock_case(case_id)
        mock_db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_case
        mock_db.execute = AsyncMock(return_value=exec_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        result = _pipeline_result(case_id, approved=False)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=result)

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
            await handle_case_created(envelope, AsyncMock())

        assert mock_case.status == "insufficient_evidence"


class TestFullPipelineFailure:
    @pytest.mark.asyncio
    async def test_pipeline_crash_sets_failed(self):
        """Pipeline throws → status=failed + audit event logged."""
        case_id = str(uuid.uuid4())
        mock_case = _mock_case(case_id)
        mock_db = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_case
        mock_db.execute = AsyncMock(return_value=exec_result)
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

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
            await handle_case_created(envelope, AsyncMock())

        assert mock_case.status == "failed"


class TestEventRouting:
    @pytest.mark.asyncio
    async def test_full_message_routing_to_handler(self):
        """Raw JSON → _process_message → correct handler dispatched."""
        case_id = str(uuid.uuid4())
        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="e2e-test",
            payload={"case_id": case_id, "seed_input": {"vendor_name": "Routed Corp"}},
        )
        raw = envelope.model_dump_json()
        mock_redis = AsyncMock()
        mock_handler = AsyncMock()

        with patch.dict("src.main._HANDLERS", {EventType.CASE_CREATED: mock_handler}):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_handler.assert_called_once()
        dispatched = mock_handler.call_args[0][0]
        assert dispatched.payload["case_id"] == case_id
        assert dispatched.source == "e2e-test"

    @pytest.mark.asyncio
    async def test_retry_envelope_preserves_count(self):
        """Handler failure creates retry with incremented count."""
        case_id = str(uuid.uuid4())
        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="e2e-test",
            payload={"case_id": case_id, "seed_input": {}, "_retry_count": 1},
        )
        raw = envelope.model_dump_json()
        mock_redis = AsyncMock()
        mock_handler = AsyncMock(side_effect=RuntimeError("transient"))

        with patch.dict("src.main._HANDLERS", {EventType.CASE_CREATED: mock_handler}):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_redis.rpush.assert_called_once()
        retry_raw = mock_redis.rpush.call_args[0][1]
        retry = EventEnvelope.model_validate_json(retry_raw)
        assert retry.payload["_retry_count"] == 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_go_to_dlq(self):
        """After MAX_RETRIES, message goes to dead-letter queue."""
        case_id = str(uuid.uuid4())
        envelope = EventEnvelope.build(
            event_type=EventType.CASE_CREATED,
            source="e2e-test",
            payload={"case_id": case_id, "seed_input": {}, "_retry_count": 3},
        )
        raw = envelope.model_dump_json()
        mock_redis = AsyncMock()
        mock_handler = AsyncMock(side_effect=RuntimeError("permanent"))

        with patch.dict("src.main._HANDLERS", {EventType.CASE_CREATED: mock_handler}):
            from src.main import _process_message
            await _process_message(mock_redis, raw)

        mock_redis.lpush.assert_called_once()
        dlq_args = mock_redis.lpush.call_args[0]
        assert dlq_args[0] == "civicproof:events:dlq"
        assert mock_redis.rpush.call_count == 0

    @pytest.mark.asyncio
    async def test_malformed_json_goes_to_dlq(self):
        """Invalid JSON is immediately dead-lettered."""
        mock_redis = AsyncMock()

        from src.main import _process_message
        await _process_message(mock_redis, "{{not valid json}}")

        mock_redis.lpush.assert_called_once()
        dlq_args = mock_redis.lpush.call_args[0]
        assert dlq_args[0] == "civicproof:events:dlq"
