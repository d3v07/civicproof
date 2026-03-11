from __future__ import annotations

import asyncio
import http.server
import logging
import signal
import threading

import redis.asyncio as aioredis
from civicproof_common.config import get_settings
from civicproof_common.db.session import async_session_context
from civicproof_common.schemas.events import EventEnvelope, EventType
from civicproof_common.telemetry import StructuredLogger, setup_telemetry

from .graph.pipeline import get_compiled_graph
from .handlers.ingest import handle_artifact_ingested
from .handlers.normalize import handle_normalize_requested
from .handlers.parse import handle_parse_requested

logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)

QUEUE_KEY = "civicproof:events"
DEAD_LETTER_KEY = "civicproof:events:dlq"
MAX_RETRIES = 3
POLL_TIMEOUT = 2


async def handle_case_created(envelope: EventEnvelope, redis_client: aioredis.Redis) -> None:
    case_id = envelope.payload["case_id"]
    seed_input = envelope.payload["seed_input"]
    _stdlib_logger.info("starting pipeline for case_id=%s", case_id)

    try:
        async with async_session_context() as db:
            await _update_case_status(db, case_id, "ingesting")

        settings = get_settings()
        graph = get_compiled_graph()
        result = await graph.ainvoke(
            {
                "case_id": case_id,
                "seed_input": seed_input,
                "retry_count": 0,
                "pipeline_log": [],
            },
            {"recursion_limit": settings.LANGGRAPH_RECURSION_LIMIT},
        )

        approved = result.get("audit_approved", False)
        async with async_session_context() as db:
            if approved:
                await _update_case_status(db, case_id, "complete")
                await _save_case_pack(db, case_id, result)
                await _log_audit_event(db, case_id, "auditor_gate", "approved",
                                       "Case pack passed all auditor rules")
            else:
                await _update_case_status(db, case_id, "insufficient_evidence")
                violations = result.get("audit_result", {}).get("violations", [])
                await _log_audit_event(db, case_id, "auditor_gate", "blocked",
                                       f"Blocked: {violations[:3]}")

        status = "approved" if approved else "blocked"
        _stdlib_logger.info("pipeline finished case_id=%s status=%s", case_id, status)

    except Exception as exc:
        _stdlib_logger.error("pipeline failed case_id=%s: %s", case_id, exc, exc_info=True)
        try:
            async with async_session_context() as db:
                await _update_case_status(db, case_id, "failed")
                await _log_audit_event(db, case_id, "orchestrator", "failed", str(exc))
        except Exception:
            _stdlib_logger.error("failed to update case status for %s", case_id)


async def _update_case_status(db, case_id: str, status: str) -> None:
    from datetime import UTC, datetime

    from civicproof_common.db.models import CaseModel
    from sqlalchemy import select

    stmt = select(CaseModel).where(CaseModel.case_id == case_id)
    row = await db.execute(stmt)
    case = row.scalar_one_or_none()
    if case:
        case.status = status
        case.updated_at = datetime.now(UTC)
        await db.flush()


async def _log_audit_event(db, case_id: str, stage: str, decision: str, detail: str) -> None:
    import uuid

    from civicproof_common.db.models import AuditEventModel

    event = AuditEventModel(
        audit_event_id=str(uuid.uuid4()),
        case_id=case_id,
        stage=stage,
        policy_decision=decision,
        detail=detail[:1000],
    )
    db.add(event)
    await db.commit()


async def _save_case_pack(db, case_id: str, result: dict) -> None:
    import uuid

    from civicproof_common.db.models import CasePackModel, CitationModel, ClaimModel

    case_pack = result.get("case_pack", {})
    claims = case_pack.get("claims", [])

    for claim in claims:
        claim_model = ClaimModel(
            claim_id=claim["claim_id"],
            case_id=case_id,
            statement=claim["statement"],
            claim_type=claim["claim_type"],
            confidence=claim["confidence"],
            is_audited=True,
            audit_passed=True,
        )
        db.add(claim_model)
        for cit_id in claim.get("citation_ids", []):
            db.add(CitationModel(
                citation_id=str(uuid.uuid4()),
                claim_id=claim["claim_id"],
                artifact_id=cit_id,
                excerpt="",
            ))

    total_citations = sum(len(c.get("citation_ids", [])) for c in claims)
    pack_hash = case_pack.get("pack_hash", "")
    db.add(CasePackModel(
        pack_id=str(uuid.uuid4()),
        case_id=case_id,
        pack_hash=pack_hash,
        storage_path=f"packs/{case_id}/{pack_hash[:16]}.json",
        claim_count=len(claims),
        citation_count=total_citations,
        all_claims_audited=True,
    ))
    await db.commit()


_HANDLERS = {
    EventType.ARTIFACT_INGESTED: handle_artifact_ingested,
    EventType.ARTIFACT_PARSE_REQUESTED: handle_parse_requested,
    EventType.ENTITY_NORMALIZE_REQUESTED: handle_normalize_requested,
    EventType.CASE_CREATED: handle_case_created,
}


async def _process_message(redis_client: aioredis.Redis, raw: str) -> None:
    try:
        envelope = EventEnvelope.model_validate_json(raw)
    except Exception as exc:
        _stdlib_logger.error("failed to parse event envelope: %s | raw=%s", exc, raw[:200])
        await redis_client.lpush(DEAD_LETTER_KEY, raw)  # type: ignore[misc]
        return

    handler = _HANDLERS.get(envelope.event_type)
    if handler is None:
        _stdlib_logger.warning("no handler for event_type=%s", envelope.event_type)
        return

    logger.info(
        "event_received",
        case_id=envelope.payload.get("case_id"),
        artifact_id=envelope.payload.get("artifact_id"),
        source=envelope.source,
        stage=envelope.event_type.value,
        policy_decision="pending",
    )

    try:
        await handler(envelope, redis_client)
    except Exception as exc:
        _stdlib_logger.error(
            "handler error event_type=%s event_id=%s: %s",
            envelope.event_type,
            envelope.event_id,
            exc,
            exc_info=True,
        )
        retry_count = envelope.payload.get("_retry_count", 0) + 1
        if retry_count <= MAX_RETRIES:
            retry_payload = dict(envelope.payload)
            retry_payload["_retry_count"] = retry_count
            retry_envelope = EventEnvelope.build(
                event_type=envelope.event_type,
                source=envelope.source,
                payload=retry_payload,
                idempotency_key=f"{envelope.idempotency_key}:retry:{retry_count}",
            )
            await redis_client.rpush(QUEUE_KEY, retry_envelope.model_dump_json())  # type: ignore[misc]
        else:
            await redis_client.lpush(DEAD_LETTER_KEY, raw)  # type: ignore[misc]


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler for Cloud Run health probes."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass  # suppress noisy access logs


def _start_health_server(port: int = 8080) -> None:
    server = http.server.HTTPServer(("0.0.0.0", port), _HealthHandler)  # noqa: S104
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    _stdlib_logger.info("health server listening on port %d", port)


async def run_worker() -> None:
    settings = get_settings()
    setup_telemetry(
        service_name="civicproof-worker",
        otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        log_level=settings.LOG_LEVEL,
    )

    # Start health endpoint for Cloud Run startup probe
    _start_health_server(settings.WORKER_HEALTH_PORT)

    redis_client = aioredis.from_url(
        settings.REDIS_URL, encoding="utf-8", decode_responses=True
    )

    _stdlib_logger.info("worker started, polling queue=%s", QUEUE_KEY)
    stop_event = asyncio.Event()

    def _handle_signal(sig, frame):
        _stdlib_logger.info("shutdown signal received")
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    consecutive_errors = 0
    try:
        while not stop_event.is_set():
            try:
                result = await redis_client.blpop([QUEUE_KEY], timeout=POLL_TIMEOUT)  # type: ignore[misc]
                consecutive_errors = 0
                if result is None:
                    continue
                _, raw = result
                await _process_message(redis_client, raw)
            except (ConnectionError, OSError, aioredis.ConnectionError) as exc:
                consecutive_errors += 1
                backoff = min(2 ** consecutive_errors, 30)
                _stdlib_logger.warning(
                    "redis connection error (attempt %d, retry in %ds): %s",
                    consecutive_errors, backoff, exc,
                )
                await asyncio.sleep(backoff)
    finally:
        await redis_client.aclose()
        _stdlib_logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())

