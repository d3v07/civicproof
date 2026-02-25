from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from civicproof_common.db.models import DataSourceModel, IngestRunModel
from civicproof_common.db.session import get_session
from civicproof_common.telemetry import StructuredLogger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)


class IngestRunRequest(BaseModel):
    source_name: str = Field(description="Name of registered data source, e.g. 'usaspending'")
    parameters: dict[str, Any] = Field(default_factory=dict)


class IngestRunResponse(BaseModel):
    run_id: str
    source_id: str
    source_name: str
    status: str
    started_at: datetime
    parameters: dict[str, Any]


@router.post("/ingest/runs", response_model=IngestRunResponse, status_code=202)
async def trigger_ingest_run(
    body: IngestRunRequest,
    db: AsyncSession = Depends(get_session),
) -> IngestRunResponse:
    ds_result = await db.execute(
        select(DataSourceModel).where(
            DataSourceModel.name == body.source_name,
            DataSourceModel.is_active,
        )
    )
    data_source = ds_result.scalar_one_or_none()
    if data_source is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "data_source_not_found", "source_name": body.source_name},
        )

    run = IngestRunModel(
        run_id=str(uuid.uuid4()),
        source_id=data_source.source_id,
        status="pending",
        parameters=body.parameters,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    logger.info(
        "ingest_run_created",
        case_id=None,
        artifact_id=None,
        source=body.source_name,
        stage="ingest_trigger",
        policy_decision="accepted",
        run_id=run.run_id,
    )

    return IngestRunResponse(
        run_id=run.run_id,
        source_id=run.source_id,
        source_name=body.source_name,
        status=run.status,
        started_at=run.started_at,
        parameters=run.parameters,
    )
