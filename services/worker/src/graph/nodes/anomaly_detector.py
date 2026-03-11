"""Anomaly Detector node — deterministic rules + LLM hypothesis generation."""

from __future__ import annotations

import json
import logging
from typing import Any

from civicproof_common.db.session import async_session_context
from langchain_core.messages import HumanMessage, SystemMessage

from ..llm import get_agent_llm
from ..state import CivicProofState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a federal procurement fraud analyst. You interpret deterministic "
    "risk signals and generate hypotheses about potential irregularities.\n\n"
    "Common procurement fraud patterns: bid rigging, shell companies, revolving door, "
    "phantom vendors, kickbacks, split purchases, change-order inflation.\n\n"
    "Rules:\n"
    "- Use ONLY 'risk signal' and 'hypothesis' language — never accusations\n"
    "- Every hypothesis must reference specific detected signals\n"
    "- Rate confidence 0.0-1.0 based on signal strength and correlation\n"
    "- If signals are benign in context, say so explicitly\n"
    "- Never use phrases like: committed fraud, guilty, is corrupt, criminals\n"
    "Return ONLY valid JSON — no markdown fences."
)


async def _build_awards_data(db, artifact_ids: list[str]) -> list[dict[str, Any]]:
    """Build simplified award data from USAspending artifacts."""
    if not artifact_ids:
        return []

    from civicproof_common.db.models import RawArtifactModel
    from sqlalchemy import select

    stmt = (
        select(RawArtifactModel)
        .where(
            RawArtifactModel.artifact_id.in_(artifact_ids),
            RawArtifactModel.source == "usaspending",
        )
        .limit(100)
    )
    result = await db.execute(stmt)
    awards = []
    for art in result.scalars():
        metadata = art.metadata_ or {}
        awards.append({
            "award_id": art.artifact_id,
            "vendor_id": metadata.get("vendor_id", ""),
            "award_amount": metadata.get("award_amount", 0),
            "awarding_agency": metadata.get("awarding_agency", ""),
            "start_date": metadata.get("start_date", ""),
            "extent_competed": metadata.get("extent_competed", ""),
        })
    return awards


def _format_risk_signals(signals: list) -> str:
    if not signals:
        return "No risk signals detected by deterministic rules."
    parts = []
    for s in signals:
        parts.append(
            f"- [{s.severity.upper()}] {s.signal_type} (score={s.score:.2f}): {s.description}"
        )
    return "\n".join(parts)


async def anomaly_detector_node(state: CivicProofState) -> dict[str, Any]:
    from ...agents.anomaly_detector import AnomalyDetectorAgent

    entity = state["primary_entity"]
    artifact_ids = state.get("artifact_ids", [])
    sources_used = state.get("sources_used", [])

    # Step 1: Deterministic detection (always runs, NEVER skipped)
    async with async_session_context() as db:
        awards_data = await _build_awards_data(db, artifact_ids)
        detector = AnomalyDetectorAgent(db)
        result = await detector.detect(
            entity_id=entity["entity_id"],
            awards=awards_data,
        )

    risk_signals = [
        {
            "signal_type": s.signal_type,
            "severity": s.severity,
            "score": s.score,
            "description": s.description,
            "evidence": s.evidence,
            "supporting_artifact_ids": s.supporting_artifact_ids,
        }
        for s in result.risk_signals
    ]

    llm_hypotheses = []

    # Step 2: LLM interprets signals and generates cross-signal hypotheses
    if result.risk_signals:
        try:
            llm = get_agent_llm(
                "anomaly_detector", temperature=0.3,
                max_tokens=2048, case_id=state.get("case_id", ""),
            )
            prompt = (
                f"Deterministic anomaly detection found these risk signals:\n"
                f"{_format_risk_signals(result.risk_signals)}\n\n"
                f"Entity: {entity['canonical_name']}\n"
                f"Award count: {len(awards_data)}\n"
                f"Sources checked: {sources_used}\n\n"
                "Analyze these signals together. Are there cross-signal patterns?\n"
                "Generate hypotheses about potential procurement irregularities.\n\n"
                "Return JSON array:\n"
                '[{"hypothesis": "...", "confidence": 0.0-1.0, '
                '"supporting_signals": ["signal_type_1", "signal_type_2"], '
                '"reasoning": "..."}]'
            )
            response = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            parsed = json.loads(response.content)
            if isinstance(parsed, list):
                llm_hypotheses = parsed[:5]
            logger.info(
                "LLM generated %d hypotheses for %s",
                len(llm_hypotheses), entity["canonical_name"],
            )
        except Exception as exc:
            logger.warning("LLM hypothesis generation failed: %s", exc)

    # Merge LLM hypotheses into risk_signals as hypothesis type
    for hyp in llm_hypotheses:
        risk_signals.append({
            "signal_type": "llm_hypothesis",
            "severity": "medium" if hyp.get("confidence", 0) < 0.7 else "high",
            "score": hyp.get("confidence", 0.5),
            "description": hyp.get("hypothesis", ""),
            "evidence": {
                "reasoning": hyp.get("reasoning", ""),
                "supporting_signals": hyp.get("supporting_signals", []),
            },
            "supporting_artifact_ids": [],
        })

    return {
        "risk_signals": risk_signals,
        "composite_risk_score": result.composite_risk_score,
        "current_stage": "anomaly_detector",
        "pipeline_log": state.get("pipeline_log", []) + [
            {"step": "anomaly_detector", "status": "completed",
             "signals": len(risk_signals),
             "llm_hypotheses": len(llm_hypotheses),
             "composite_score": result.composite_risk_score}
        ],
    }
