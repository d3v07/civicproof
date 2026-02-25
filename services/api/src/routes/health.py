from __future__ import annotations

import logging

from civicproof_common.db.session import get_session
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.error("readiness db check failed: %s", exc)
        checks["postgres"] = "error"

    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            logger.error("readiness redis check failed: %s", exc)
            checks["redis"] = "error"
    else:
        checks["redis"] = "not_configured"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}
