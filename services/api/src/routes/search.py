from __future__ import annotations

import logging
from typing import Any

from civicproof_common.db.models import EntityModel, RawArtifactModel
from civicproof_common.db.session import get_session
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)


class EntitySearchResult(BaseModel):
    entity_id: str
    entity_type: str
    canonical_name: str
    uei: str | None
    cage_code: str | None
    aliases: list[str]


class ArtifactSearchResult(BaseModel):
    artifact_id: str
    source: str
    source_url: str
    content_hash: str
    retrieved_at: str
    metadata: dict[str, Any]


class PaginatedEntityResults(BaseModel):
    items: list[EntitySearchResult]
    total: int
    page: int
    page_size: int


class PaginatedArtifactResults(BaseModel):
    items: list[ArtifactSearchResult]
    total: int
    page: int
    page_size: int


@router.get("/search/entities", response_model=PaginatedEntityResults)
async def search_entities(
    q: str = Query(min_length=1, max_length=200),
    entity_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> PaginatedEntityResults:
    offset = (page - 1) * page_size
    stmt = select(EntityModel).where(
        or_(
            EntityModel.canonical_name.ilike(f"%{q}%"),
            EntityModel.uei == q,
            EntityModel.cage_code == q,
        )
    )
    if entity_type:
        stmt = stmt.where(EntityModel.entity_type == entity_type)

    count_result = await db.execute(stmt.with_only_columns(EntityModel.entity_id))
    total = len(count_result.all())

    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = [
        EntitySearchResult(
            entity_id=r.entity_id,
            entity_type=r.entity_type,
            canonical_name=r.canonical_name,
            uei=r.uei,
            cage_code=r.cage_code,
            aliases=r.aliases or [],
        )
        for r in rows
    ]

    return PaginatedEntityResults(items=items, total=total, page=page, page_size=page_size)


@router.get("/search/artifacts", response_model=PaginatedArtifactResults)
async def search_artifacts(
    q: str = Query(min_length=1, max_length=200),
    source: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> PaginatedArtifactResults:
    offset = (page - 1) * page_size
    stmt = select(RawArtifactModel).where(
        or_(
            RawArtifactModel.source_url.ilike(f"%{q}%"),
            RawArtifactModel.content_hash == q,
        )
    )
    if source:
        stmt = stmt.where(RawArtifactModel.source == source)

    count_result = await db.execute(stmt.with_only_columns(RawArtifactModel.artifact_id))
    total = len(count_result.all())

    stmt = stmt.offset(offset).limit(page_size).order_by(RawArtifactModel.retrieved_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = [
        ArtifactSearchResult(
            artifact_id=r.artifact_id,
            source=r.source,
            source_url=r.source_url,
            content_hash=r.content_hash,
            retrieved_at=r.retrieved_at.isoformat(),
            metadata=r.metadata_ or {},
        )
        for r in rows
    ]

    return PaginatedArtifactResults(items=items, total=total, page=page, page_size=page_size)
