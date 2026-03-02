from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from civicproof_common.db.models import (
    AuditEventModel,
    CaseModel,
    ClaimModel,
)
from civicproof_common.db.session import get_session
from civicproof_common.hashing import content_hash
from civicproof_common.schemas.cases import CaseStatus
from civicproof_common.telemetry import StructuredLogger
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

try:
    from ..renderers.pdf import render_case_pack_pdf as _render_pdf
except ImportError:
    from renderers.pdf import render_case_pack_pdf as _render_pdf  # type: ignore[no-redef]

router = APIRouter()
logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)


class CreateCaseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    seed_input: dict[str, Any] = Field(
        description="Seed data: vendor_name, uei, cage_code, award_id, or tip_text"
    )


class CaseResponse(BaseModel):
    case_id: str
    title: str
    status: str
    seed_input: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int
    page: int
    page_size: int


class CasePackResponse(BaseModel):
    case_id: str
    claims: list[dict]
    citations: list[dict]
    audit_events: list[dict]
    generated_at: datetime
    pack_hash: str | None


def _row_to_case_response(row: CaseModel) -> CaseResponse:
    return CaseResponse(
        case_id=row.case_id,
        title=row.title,
        status=row.status,
        seed_input=row.seed_input,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/cases", response_model=CaseListResponse)
async def list_cases(
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> CaseListResponse:
    count_q = select(func.count()).select_from(CaseModel)
    rows_q = select(CaseModel).order_by(CaseModel.created_at.desc())
    if status:
        count_q = count_q.where(CaseModel.status == status)
        rows_q = rows_q.where(CaseModel.status == status)

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    rows = (await db.execute(rows_q.offset(offset).limit(page_size))).scalars().all()

    return CaseListResponse(
        items=[_row_to_case_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/cases", response_model=CaseResponse, status_code=201)
async def create_case(
    body: CreateCaseRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    seed_str = json.dumps(body.seed_input, sort_keys=True)
    idempotency_key = content_hash(f"{body.title}:{seed_str}".encode())

    existing = await db.execute(
        select(CaseModel).where(CaseModel.status != CaseStatus.FAILED)
    )
    for row in existing.scalars():
        row_seed_str = json.dumps(row.seed_input, sort_keys=True)
        row_key = content_hash(f"{row.title}:{row_seed_str}".encode())
        if row_key == idempotency_key:
            return _row_to_case_response(row)

    case = CaseModel(
        case_id=str(uuid.uuid4()),
        title=body.title,
        status=CaseStatus.PENDING.value,
        seed_input=body.seed_input,
    )
    db.add(case)
    await db.flush()

    audit = AuditEventModel(
        audit_event_id=str(uuid.uuid4()),
        case_id=case.case_id,
        stage="intake",
        policy_decision="accepted",
        detail="Case created from seed input",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(case)

    logger.info(
        "case_created",
        case_id=case.case_id,
        source="api",
        stage="intake",
        policy_decision="accepted",
        artifact_id=None,
    )
    return _row_to_case_response(case)


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    result = await db.execute(select(CaseModel).where(CaseModel.case_id == case_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "case_not_found", "case_id": case_id},
        )
    return _row_to_case_response(row)


@router.get("/cases/{case_id}/pack", response_model=CasePackResponse)
async def get_case_pack(
    case_id: str,
    db: AsyncSession = Depends(get_session),
) -> CasePackResponse:
    result = await db.execute(
        select(CaseModel)
        .where(CaseModel.case_id == case_id)
        .options(
            selectinload(CaseModel.claims).selectinload(ClaimModel.citations),
            selectinload(CaseModel.audit_events),
            selectinload(CaseModel.case_packs),
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "case_not_found", "case_id": case_id},
        )

    if case.status not in (CaseStatus.COMPLETE.value, CaseStatus.AUDITING.value):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "pack_not_ready",
                "case_id": case_id,
                "status": case.status,
            },
        )

    latest_pack = (
        sorted(case.case_packs, key=lambda p: p.generated_at, reverse=True)[0]
        if case.case_packs
        else None
    )

    claims_out = [
        {
            "claim_id": c.claim_id,
            "statement": c.statement,
            "claim_type": c.claim_type,
            "confidence": c.confidence,
            "is_audited": c.is_audited,
            "audit_passed": c.audit_passed,
        }
        for c in case.claims
    ]

    citations_out = [
        {
            "citation_id": cit.citation_id,
            "claim_id": cit.claim_id,
            "artifact_id": cit.artifact_id,
            "excerpt": cit.excerpt,
            "page_ref": cit.page_ref,
        }
        for claim in case.claims
        for cit in claim.citations
    ]

    audit_events_out = [
        {
            "audit_event_id": a.audit_event_id,
            "stage": a.stage,
            "policy_decision": a.policy_decision,
            "detail": a.detail,
            "timestamp": a.timestamp.isoformat(),
        }
        for a in case.audit_events
    ]

    return CasePackResponse(
        case_id=case_id,
        claims=claims_out,
        citations=citations_out,
        audit_events=audit_events_out,
        generated_at=latest_pack.generated_at if latest_pack else datetime.now(UTC),
        pack_hash=latest_pack.pack_hash if latest_pack else None,
    )


@router.get("/cases/{case_id}/pack.pdf")
async def get_case_pack_pdf(
    case_id: str,
    db: AsyncSession = Depends(get_session),
) -> Response:
    result = await db.execute(
        select(CaseModel)
        .where(CaseModel.case_id == case_id)
        .options(
            selectinload(CaseModel.claims).selectinload(ClaimModel.citations),
            selectinload(CaseModel.audit_events),
            selectinload(CaseModel.case_packs),
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "case_not_found", "case_id": case_id},
        )

    if case.status not in (CaseStatus.COMPLETE.value, CaseStatus.AUDITING.value):
        raise HTTPException(
            status_code=409,
            detail={"error": "pack_not_ready", "case_id": case_id, "status": case.status},
        )

    latest_pack = (
        sorted(case.case_packs, key=lambda p: p.generated_at, reverse=True)[0]
        if case.case_packs
        else None
    )

    claims_data = [
        {
            "claim_id": c.claim_id,
            "statement": c.statement,
            "claim_type": c.claim_type,
            "confidence": c.confidence,
        }
        for c in case.claims
    ]
    citations_data = [
        {
            "citation_id": cit.citation_id,
            "claim_id": cit.claim_id,
            "artifact_id": cit.artifact_id,
            "excerpt": cit.excerpt,
        }
        for claim in case.claims
        for cit in claim.citations
    ]
    audit_data = [
        {
            "audit_event_id": a.audit_event_id,
            "stage": a.stage,
            "policy_decision": a.policy_decision,
            "detail": a.detail,
            "timestamp": a.timestamp.isoformat(),
        }
        for a in case.audit_events
    ]

    pdf_bytes = _render_pdf(
        case_id=case_id,
        title=case.title,
        claims=claims_data,
        citations=citations_data,
        audit_events=audit_data,
        pack_hash=latest_pack.pack_hash if latest_pack else None,
        generated_at=latest_pack.generated_at if latest_pack else None,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="civicproof_{case_id}.pdf"'},
    )
