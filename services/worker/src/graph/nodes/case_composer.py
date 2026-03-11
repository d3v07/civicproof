"""Case Composer node — LLM-powered narrative generation (Phase 1)."""

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
    "You are a legal analyst composing investigative case dossiers about federal procurement. "
    "Write in a formal, objective style suitable for whistleblower complaints and FOIA requests. "
    "CRITICAL RULES:\n"
    "- Every factual statement must cite an artifact_id from the provided list\n"
    "- Use ONLY 'risk signal' and 'hypothesis' language — never accusations\n"
    "- Never use phrases like: committed fraud, guilty of, is defrauding, criminals, is corrupt\n"
    "- Claims without artifact support MUST be typed as 'hypothesis'\n"
    "- Include the disclaimer: 'This document contains risk signals and hypotheses only; "
    "it does not constitute an accusation of wrongdoing.'\n"
    "Return ONLY valid JSON — no markdown fences, no commentary."
)


def _summarize_awards(awards: list[dict]) -> str:
    if not awards:
        return "No award data available."
    total = sum(float(a.get("award_amount", 0) or 0) for a in awards)
    agencies = {a.get("awarding_agency", "Unknown") for a in awards}
    return f"{len(awards)} awards totaling ${total:,.2f} from {len(agencies)} agencies"


def _format_risk_signals(signals: list[dict]) -> str:
    if not signals:
        return "No risk signals detected."
    parts = []
    for s in signals:
        parts.append(
            f"- [{s.get('severity', 'unknown').upper()}] "
            f"{s.get('signal_type', '')}: {s.get('description', '')}"
        )
    return "\n".join(parts)


async def case_composer_node(state: CivicProofState) -> dict[str, Any]:
    from ...agents.case_composer import CaseComposerAgent

    entity = state["primary_entity"]
    risk_signals = state.get("risk_signals", [])
    sources_used = state.get("sources_used", [])
    artifact_ids = state.get("artifact_ids", [])
    graph_result = state.get("graph_result", {})

    # Build awards data for deterministic composition
    async with async_session_context() as db:
        from .anomaly_detector import _build_awards_data
        awards_data = await _build_awards_data(db, artifact_ids)

    # Step 1: Deterministic composition (existing logic, always runs)
    composer = CaseComposerAgent()
    entity_profile = {
        "entity_id": entity["entity_id"],
        "canonical_name": entity["canonical_name"],
        "entity_type": entity.get("entity_type", "vendor"),
        "uei": entity.get("uei"),
        "cage_code": entity.get("cage_code"),
    }
    composition = composer.compose(
        case_id=state["case_id"],
        entity_profile=entity_profile,
        artifact_ids=artifact_ids,
        risk_signals=risk_signals,
        awards_data=awards_data,
        sources_used=sources_used,
    )
    pack = composition.case_pack

    # Step 2: LLM-enhanced narrative (title + summary + executive overview)
    try:
        llm = get_agent_llm(
            "case_composer", temperature=0.4,
            max_tokens=4096, case_id=state.get("case_id", ""),
        )
        prompt = (
            f"Entity: {entity['canonical_name']}\n"
            f"Risk Signals:\n{_format_risk_signals(risk_signals)}\n"
            f"Evidence Sources: {', '.join(sources_used)}\n"
            f"Award Summary: {_summarize_awards(awards_data)}\n"
            f"Graph Centrality: {json.dumps(graph_result.get('centrality_scores', {}))}\n\n"
            f"Available artifact_ids for citation (use these EXACTLY):\n"
            f"{json.dumps(artifact_ids[:20])}\n\n"
            "Write a JSON object with:\n"
            '{"title": "...", "summary": "2-3 paragraph executive summary", '
            '"hypotheses": [{"statement": "...", "confidence": 0.0-1.0, '
            '"supporting_signal_types": ["..."]}]}'
        )
        response = await llm.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        llm_output = json.loads(response.content)

        # Merge LLM narrative into deterministic pack
        if llm_output.get("title"):
            pack.title = llm_output["title"]
        if llm_output.get("summary"):
            pack.summary = llm_output["summary"]

        # Add LLM hypotheses as additional claims
        from civicproof_common.schemas.cases import ClaimType
        for idx, hyp in enumerate(llm_output.get("hypotheses", [])[:5]):
            from ...agents.case_composer import ComposedClaim
            pack.claims.append(ComposedClaim(
                claim_id=composer._deterministic_claim_id(
                    state["case_id"], f"llm_hypothesis_{idx}", hyp.get("statement", "")
                ),
                statement=hyp.get("statement", ""),
                claim_type=ClaimType.HYPOTHESIS.value,
                confidence=hyp.get("confidence", 0.5),
                citation_ids=[],
                artifact_ids=[],
            ))

        # Recompute hash after LLM additions
        pack.compute_hash()

    except Exception as exc:
        logger.warning("LLM narrative generation failed, using deterministic output: %s", exc)

    # Build pack dict for downstream nodes
    pack_dict = {
        "case_id": pack.case_id,
        "title": pack.title,
        "summary": pack.summary,
        "claims": [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "claim_type": c.claim_type,
                "confidence": c.confidence,
                "citation_ids": c.citation_ids,
                "artifact_ids": c.artifact_ids,
            }
            for c in pack.claims
        ],
        "risk_signals": pack.risk_signals,
        "entity_profile": pack.entity_profile,
        "evidence_summary": pack.evidence_summary,
        "timeline": pack.timeline,
        "sources_used": pack.sources_used,
        "pack_hash": pack.pack_hash,
    }

    claims_list = pack_dict["claims"]

    return {
        "case_pack": pack_dict,
        "claims": claims_list,
        "current_stage": "case_composer",
        "pipeline_log": state.get("pipeline_log", []) + [
            {"step": "case_composer", "status": "completed",
             "claims": len(claims_list), "hash": pack.pack_hash}
        ],
    }
