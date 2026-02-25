from __future__ import annotations

import time
import uuid

from civicproof_common.telemetry import get_tracer
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_tracer = get_tracer("civicproof.api")


class TelemetryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        with _tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            kind=trace.SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.request_id", request_id)

            start = time.perf_counter()
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000

            span.set_attribute("http.status_code", response.status_code)
            span.set_attribute("http.duration_ms", round(elapsed_ms, 2))

            response.headers["X-Request-ID"] = request_id
            return response
