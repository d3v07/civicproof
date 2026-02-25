from __future__ import annotations

import logging
import sys
from datetime import UTC
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_REQUIRED_LOG_FIELDS = frozenset(
    ["case_id", "artifact_id", "source", "stage", "policy_decision"]
)

_tracer_provider: TracerProvider | None = None


def setup_telemetry(
    service_name: str,
    otlp_endpoint: str | None = None,
    log_level: str = "INFO",
) -> None:
    global _tracer_provider

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    _configure_json_logging(log_level)


def _configure_json_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_StructuredFormatter())
        root_logger.addHandler(handler)


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in _REQUIRED_LOG_FIELDS:
            payload[field] = getattr(record, field, None)

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


class StructuredLogger:
    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _make_extra(self, **kwargs: Any) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        for field in _REQUIRED_LOG_FIELDS:
            extra[field] = kwargs.get(field)
        extra.update(kwargs)
        return extra

    def info(self, msg: str, **kwargs: Any) -> None:
        self._logger.info(msg, extra=self._make_extra(**kwargs))

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._logger.warning(msg, extra=self._make_extra(**kwargs))

    def error(self, msg: str, **kwargs: Any) -> None:
        self._logger.error(msg, extra=self._make_extra(**kwargs))

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._logger.debug(msg, extra=self._make_extra(**kwargs))
