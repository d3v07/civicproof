"""Auditor Gate node — deterministic gate, LLM CANNOT override."""

from __future__ import annotations

import logging
from typing import Any

from civicproof_common.db.session import async_session_context
from civicproof_common.db.models import RawArtifactModel
from sqlalchemy import select

from ..state import CivicProofState

logger = logging.getLogger(__name__)


async def _get_artifact_hashes(db, artifact_ids: list[str]) -> dict[str, str]:
    if not artifact_ids:
        return {}
    stmt = select(RawArtifactModel).where(
        RawArtifactModel.artifact_id.in_(artifact_ids)
    )
    result = await db.execute(stmt)
    return {
        art.artifact_id: art.content_hash
        for art in result.scalars()
        if art.content_hash
    }


async def auditor_gate_node(state: CivicProofState) -> dict[str, Any]:
    from ...agents.auditor import AuditorGate

    case_pack = state["case_pack"]
    artifact_ids = state.get("artifact_ids", [])

    async with async_session_context() as db:
        artifact_hashes = await _get_artifact_hashes(db, artifact_ids)

    auditor = AuditorGate(
        valid_artifact_ids=set(artifact_ids),
        artifact_hashes=artifact_hashes,
        min_sources=2,
    )

    audit_result = auditor.audit(case_pack)

    if not audit_result.approved:
        return {
            "audit_result": {
                "approved": False,
                "violations": audit_result.violations[:5],
                "summary": audit_result.summary,
            },
            "audit_approved": False,
            "retry_count": state.get("retry_count", 0) + 1,
            "error": f"Blocked: {audit_result.violations[:3]}",
            "current_stage": "auditor_gate",
            "pipeline_log": state.get("pipeline_log", []) + [
                {"step": "auditor_gate", "status": "blocked",
                 "violations": len(audit_result.violations)}
            ],
        }

    return {
        "audit_result": {
            "approved": True,
            "violations": [],
            "summary": audit_result.summary,
        },
        "audit_approved": True,
        "current_stage": "auditor_gate",
        "pipeline_log": state.get("pipeline_log", []) + [
            {"step": "auditor_gate", "status": "approved"}
        ],
    }
