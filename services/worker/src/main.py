from __future__ import annotations

import asyncio
import http.server
import logging
import signal
import threading

import redis.asyncio as aioredis
from civicproof_common.config import get_settings
from civicproof_common.schemas.events import EventEnvelope, EventType
from civicproof_common.telemetry import StructuredLogger, setup_telemetry

from .handlers.ingest import handle_artifact_ingested
from .handlers.normalize import handle_normalize_requested
from .handlers.parse import handle_parse_requested

logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)

QUEUE_KEY = "civicproof:events"
DEAD_LETTER_KEY = "civicproof:events:dlq"
MAX_RETRIES = 3
POLL_TIMEOUT = 2


_HANDLERS = {
    EventType.ARTIFACT_INGESTED: handle_artifact_ingested,
    EventType.ARTIFACT_PARSE_REQUESTED: handle_parse_requested,
    EventType.ENTITY_NORMALIZE_REQUESTED: handle_normalize_requested,
}


async def _process_message(redis_client: aioredis.Redis, raw: str) -> None:
    try:
        envelope = EventEnvelope.model_validate_json(raw)
    except Exception as exc:
        _stdlib_logger.error("failed to parse event envelope: %s | raw=%s", exc, raw[:200])
        await redis_client.lpush(DEAD_LETTER_KEY, raw)
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
            await redis_client.rpush(QUEUE_KEY, retry_envelope.model_dump_json())
        else:
            await redis_client.lpush(DEAD_LETTER_KEY, raw)


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
    _start_health_server(int(settings.PORT if hasattr(settings, "PORT") else 8080))

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

    try:
        while not stop_event.is_set():
            result = await redis_client.blpop(QUEUE_KEY, timeout=POLL_TIMEOUT)
            if result is None:
                continue
            _, raw = result
            await _process_message(redis_client, raw)
    finally:
        await redis_client.aclose()
        _stdlib_logger.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())

