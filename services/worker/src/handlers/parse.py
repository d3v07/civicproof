from __future__ import annotations

import logging
import uuid

import redis.asyncio as aioredis
from civicproof_common.db.models import ParsedDocModel
from civicproof_common.db.session import get_session
from civicproof_common.idempotency import IdempotencyGuard
from civicproof_common.schemas.events import EventEnvelope, EventType
from civicproof_common.storage.object_store import build_object_store
from civicproof_common.telemetry import StructuredLogger

logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)

WORKER_QUEUE_KEY = "civicproof:events"


def _extract_text(raw_bytes: bytes, doc_type: str) -> tuple[str, dict]:
    text = ""
    structured: dict = {}

    try:
        decoded = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return text, structured

    json_doc_types = ("contract_award", "sam_registration", "fec_filing")
    if doc_type in json_doc_types or decoded.lstrip().startswith("{"):
        import json
        try:
            data = json.loads(decoded)
            structured = data if isinstance(data, dict) else {"items": data}
            text_parts = []
            _flatten_json_to_text(data, text_parts)
            text = " ".join(text_parts)
        except json.JSONDecodeError:
            text = decoded
    else:
        text = decoded

    return text[:1_000_000], structured


def _flatten_json_to_text(obj, parts: list, depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, str):
        if obj.strip():
            parts.append(obj.strip())
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_json_to_text(v, parts, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _flatten_json_to_text(item, parts, depth + 1)
    elif obj is not None:
        parts.append(str(obj))


async def handle_parse_requested(
    envelope: EventEnvelope,
    redis_client: aioredis.Redis,
) -> None:
    payload = envelope.payload
    artifact_id = payload.get("artifact_id", "")
    source = payload.get("source", "unknown")
    storage_path = payload.get("storage_path", "")
    doc_type = payload.get("doc_type", "unknown")

    guard = IdempotencyGuard(redis_client)
    if not await guard.check_and_set(envelope.idempotency_key):
        logger.info(
            "parse_duplicate",
            case_id=None,
            artifact_id=artifact_id,
            source=source,
            stage="parse",
            policy_decision="deduplicated",
        )
        return

    if not artifact_id or not storage_path:
        _stdlib_logger.error("parse payload missing artifact_id or storage_path")
        return

    object_store = build_object_store()
    try:
        raw_bytes = await object_store.get_artifact(storage_path)
    except Exception as exc:
        _stdlib_logger.error("failed to fetch artifact %s from store: %s", artifact_id, exc)
        return

    extracted_text, structured_data = _extract_text(raw_bytes, doc_type)

    doc_id = str(uuid.uuid4())
    async for db in get_session():
        from sqlalchemy import select
        existing = await db.execute(
            select(ParsedDocModel).where(ParsedDocModel.artifact_id == artifact_id)
        )
        if existing.scalar_one_or_none() is None:
            parsed = ParsedDocModel(
                doc_id=doc_id,
                artifact_id=artifact_id,
                doc_type=doc_type,
                extracted_text=extracted_text,
                structured_data=structured_data,
            )
            db.add(parsed)
            await db.commit()

    normalize_event = EventEnvelope.build(
        event_type=EventType.ENTITY_NORMALIZE_REQUESTED,
        source="worker.parse",
        payload={
            "artifact_id": artifact_id,
            "doc_id": doc_id,
            "source": source,
            "text_snippet": extracted_text[:2000],
            "structured_data": structured_data,
        },
        idempotency_key=f"normalize:{artifact_id}",
    )
    await redis_client.rpush(WORKER_QUEUE_KEY, normalize_event.model_dump_json())

    logger.info(
        "artifact_parsed",
        case_id=None,
        artifact_id=artifact_id,
        source=source,
        stage="parse",
        policy_decision="stored",
        doc_id=doc_id,
        text_length=len(extracted_text),
    )
