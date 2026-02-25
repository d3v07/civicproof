from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from civicproof_common.config import get_settings
from civicproof_common.telemetry import setup_telemetry
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .cache import SemanticCache
from .policies.budget import BudgetEnforcer
from .policies.content_filter import ContentFilter
from .policies.rate_limit import LLMRateLimiter
from .router import ModelRouter, TaskType


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_telemetry(
        service_name="civicproof-gateway",
        otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        log_level=settings.LOG_LEVEL,
    )
    redis_client = aioredis.from_url(
        settings.REDIS_URL, encoding="utf-8", decode_responses=True
    )
    app.state.redis = redis_client
    app.state.router = ModelRouter()
    app.state.cache = SemanticCache(redis_client)
    app.state.budget = BudgetEnforcer(redis_client)
    app.state.content_filter = ContentFilter(pii_redaction_enabled=settings.PII_REDACTION_ENABLED)
    app.state.llm_rate_limiter = LLMRateLimiter(redis_client)
    yield
    await redis_client.aclose()


app = FastAPI(
    title="CivicProof LLM Gateway",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


class CompletionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    task_type: TaskType = TaskType.COMPLETION
    system_instruction: str | None = None
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    case_id: str | None = None
    skip_cache: bool = False


class EmbeddingRequest(BaseModel):
    text: str = Field(min_length=1, max_length=32_000)
    case_id: str | None = None


@app.post("/v1/completions")
async def completions(body: CompletionRequest, request: Request) -> dict[str, Any]:
    cf: ContentFilter = request.app.state.content_filter
    filter_result = cf.filter_input(body.prompt)
    if not filter_result.allowed:
        raise HTTPException(
            status_code=400,
            detail={"error": "input_blocked", "reasons": filter_result.blocked_reasons},
        )

    rate_limiter: LLMRateLimiter = request.app.state.llm_rate_limiter
    allowed, count = await rate_limiter.check_and_increment(body.case_id)
    if not allowed:
        raise HTTPException(status_code=429, detail={"error": "llm_rate_limit_exceeded"})

    if body.case_id:
        budget: BudgetEnforcer = request.app.state.budget
        within_budget, spent = await budget.check_case_budget(body.case_id)
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail={"error": "budget_exceeded", "spent_usd": spent},
            )

    cache: SemanticCache = request.app.state.cache
    if not body.skip_cache:
        cached = await cache.get(
            filter_result.sanitized_text,
            body.task_type.value,
            body.system_instruction,
        )
        if cached is not None:
            cached["cache_hit"] = True
            return cached

    router: ModelRouter = request.app.state.router
    result = await router.complete(
        prompt=filter_result.sanitized_text,
        task_type=body.task_type,
        system_instruction=body.system_instruction,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        case_id=body.case_id,
    )

    output_filter = cf.filter_output(result.get("text", ""))
    result["text"] = output_filter.sanitized_text

    if not body.skip_cache:
        await cache.set(
            filter_result.sanitized_text,
            body.task_type.value,
            result,
            body.system_instruction,
        )

    usage = result.get("usage", {})
    total_tokens = usage.get("total_tokens", 0)
    if total_tokens > 0 and body.case_id:
        budget = request.app.state.budget
        await budget.record_usage(body.case_id, total_tokens, result.get("provider", "unknown"))

    result["cache_hit"] = False
    return result


@app.post("/v1/embeddings")
async def embeddings(body: EmbeddingRequest, request: Request) -> dict[str, Any]:
    cf: ContentFilter = request.app.state.content_filter
    filter_result = cf.filter_input(body.text)
    if not filter_result.allowed:
        raise HTTPException(
            status_code=400,
            detail={"error": "input_blocked", "reasons": filter_result.blocked_reasons},
        )

    router: ModelRouter = request.app.state.router
    return await router.embed(text=filter_result.sanitized_text, case_id=body.case_id)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
