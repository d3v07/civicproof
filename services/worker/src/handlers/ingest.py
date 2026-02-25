from __future__ import annotations

import logging
import uuid

import redis.asyncio as aioredis
from civicproof_common.db.models import RawArtifactModel
from civicproof_common.db.session import get_session
from civicproof_common.hashing import content_hash, verify_hash
from civicproof_common.idempotency import IdempotencyGuard
from civicproof_common.schemas.events import EventEnvelope, EventType
from civicproof_common.storage.object_store import build_object_store
from civicproof_common.telemetry import StructuredLogger

logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)

WORKER_QUEUE_KEY = "civicproof:events"


async def handle_artifact_ingested(
    envelope: EventEnvelope,
    redis_client: aioredis.Redis,
) -> None:
    payload = envelope.payload
    artifact_id = payload.get("artifact_id") or str(uuid.uuid4())
    source = payload.get("source", "unknown")
    source_url = payload.get("source_url", "")
    raw_data_hex = payload.get("raw_data_hex", "")
    ingest_run_id = payload.get("ingest_run_id")

    guard = IdempotencyGuard(redis_client)
    if not await guard.check_and_set(envelope.idempotency_key):
        logger.info(
            "artifact_ingested_duplicate",
            case_id=None,
            artifact_id=artifact_id,
            source=source,
            stage="ingest",
            policy_decision="deduplicated",
        )
        return

    if not raw_data_hex:
        _stdlib_logger.error(
            "artifact.ingested payload missing raw_data_hex, artifact_id=%s",
            artifact_id,
        )
        return

    raw_bytes = bytes.fromhex(raw_data_hex)
    hash_value = content_hash(raw_bytes)

    provided_hash = payload.get("content_hash")
    if provided_hash and not verify_hash(raw_bytes, provided_hash):
        _stdlib_logger.error(
            "content hash mismatch artifact_id=%s provided=%s computed=%s",
            artifact_id,
            provided_hash,
            hash_value,
        )
        return

    object_store = build_object_store()
    storage_key = object_store.storage_key(source, hash_value)

    if not await object_store.artifact_exists(hash_value):
        metadata = {
            "source": source,
            "source_url": source_url,
            "artifact_id": artifact_id,
            "content_hash": hash_value,
        }
        await object_store.put_artifact(storage_key, raw_bytes, metadata)

    async for db in get_session():
        from sqlalchemy import select
        existing = await db.execute(
            select(RawArtifactModel).where(
                RawArtifactModel.source == source,
                RawArtifactModel.content_hash == hash_value,
            )
        )
        if existing.scalar_one_or_none() is None:
            artifact_row = RawArtifactModel(
                artifact_id=artifact_id,
                ingest_run_id=ingest_run_id,
                source=source,
                source_url=source_url,
                content_hash=hash_value,
                storage_path=storage_key,
                metadata_=payload.get("metadata", {}),
            )
            db.add(artifact_row)
            await db.commit()

    parse_event = EventEnvelope.build(
        event_type=EventType.ARTIFACT_PARSE_REQUESTED,
        source="worker.ingest",
        payload={
            "artifact_id": artifact_id,
            "source": source,
            "storage_path": storage_key,
            "doc_type": payload.get("doc_type", "unknown"),
        },
        idempotency_key=f"parse:{artifact_id}",
    )
    await redis_client.rpush(WORKER_QUEUE_KEY, parse_event.model_dump_json())

    logger.info(
        "artifact_stored",
        case_id=None,
        artifact_id=artifact_id,
        source=source,
        stage="ingest",
        policy_decision="stored",
        storage_path=storage_key,
    )
