from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_RATE_LIMIT_PREFIX = "api_ratelimit:"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, requests_per_minute: int = 60) -> None:
        super().__init__(app)
        self._rpm = requests_per_minute
        self._window = 60

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in ("/health", "/ready"):
            return await call_next(request)

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        window_key = int(time.time()) // self._window
        key = f"{_RATE_LIMIT_PREFIX}{client_ip}:{window_key}"

        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self._window)

        remaining = max(0, self._rpm - count)
        reset_at = (window_key + 1) * self._window

        if count > self._rpm:
            retry_after = reset_at - int(time.time())
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "retry_after": retry_after},
                headers={
                    "X-RateLimit-Limit": str(self._rpm),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                    "Retry-After": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self._rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response
