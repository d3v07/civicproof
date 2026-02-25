from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from civicproof_common.db.session import get_session
from civicproof_common.storage.object_store import ObjectStore, build_object_store
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

_object_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _object_store
    if _object_store is None:
        _object_store = build_object_store()
    return _object_store


async def get_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[AsyncSession, None]:
    yield session


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis
