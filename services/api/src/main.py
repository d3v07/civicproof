from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from civicproof_common.config import get_settings
from civicproof_common.db.session import dispose_engine
from civicproof_common.telemetry import setup_telemetry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware.rate_limit import RateLimitMiddleware
from .middleware.telemetry import TelemetryMiddleware
from .routes import cases, health, ingest, search

_redis_pool: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_pool
    settings = get_settings()
    setup_telemetry(
        service_name="civicproof-api",
        otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        log_level=settings.LOG_LEVEL,
    )
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    app.state.redis = _redis_pool
    yield
    if _redis_pool:
        await _redis_pool.aclose()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CivicProof API",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_middleware(TelemetryMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.API_RATE_LIMIT_PER_MINUTE,
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(cases.router, prefix="/v1", tags=["cases"])
    app.include_router(search.router, prefix="/v1", tags=["search"])
    app.include_router(ingest.router, prefix="/v1", tags=["ingest"])

    return app


app = create_app()
