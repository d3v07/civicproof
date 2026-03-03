"""Evidence Retrieval node — LLM plans search strategy, existing agent executes."""

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
    "You are a federal data source expert for investigative research. "
    "You know what each data source returns and what search terms work best.\n\n"
    "Available sources:\n"
    "- usaspending: Federal contracts/grants by recipient name. Best for award amounts, agencies, competition data.\n"
    "- sam_gov: Contract opportunities. Best for active solicitations, set-asides.\n"
    "- sec_edgar: SEC filings (10-K, 10-Q, 8-K). Best for publicly traded companies.\n"
    "- doj: DOJ press releases on fraud cases. Best for enforcement actions.\n"
    "- openfec: Political committees and campaign contributions. Best for political donation links.\n"
    "- oversight_gov: Inspector General reports. Best for agency-level audit findings.\n\n"
    "Plan queries based on entity type and likely fraud patterns. "
    "Never fabricate data — only plan search queries.\n"
    "Return ONLY valid JSON — no markdown fences."
)


async def evidence_retrieval_node(state: CivicProofState) -> dict[str, Any]:
    from ...agents.evidence_retrieval import EvidenceRetrievalAgent

    entity = state["primary_entity"]

    # Step 1: Existing deterministic retrieval (always runs)
    async with async_session_context() as db:
        retriever = EvidenceRetrievalAgent(db)
        result = await retriever.retrieve(
            entity_id=entity["entity_id"],
            entity_name=entity["canonical_name"],
            entity_uei=entity.get("uei"),
        )

    manifest = result.manifest
    strategy_log = []

    # Step 2: LLM plans additional search strategy for missing/stale sources
    if manifest.missing_sources or manifest.stale_sources:
        try:
            llm = get_agent_llm("evidence_retrieval", temperature=0.2, max_tokens=2048, case_id=state.get("case_id", ""))
            prompt = (
                f"Entity: {entity['canonical_name']}\n"
                f"Type: {entity.get('entity_type', 'vendor')}\n"
                f"UEI: {entity.get('uei', 'N/A')}\n"
                f"Aliases: {entity.get('aliases', [])}\n\n"
                f"Already covered sources: {list(manifest.artifacts_by_source.keys())}\n"
                f"Missing sources: {manifest.missing_sources}\n"
                f"Stale sources (need refresh): {manifest.stale_sources}\n\n"
                "For each missing/stale source, suggest the best search query.\n"
                "Consider name variations and entity type for query optimization.\n"
                "Return JSON array: "
                '[{"source": "...", "query": "...", "priority": 1-5, "reasoning": "..."}]'
            )
            response = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            strategy = json.loads(response.content)
            strategy_log = strategy if isinstance(strategy, list) else []
            logger.info(
                "LLM search strategy for %s: %d queries planned",
                entity["canonical_name"], len(strategy_log),
            )
        except Exception as exc:
            logger.warning("LLM search strategy failed, using defaults: %s", exc)
            strategy_log = [{"source": s, "query": entity["canonical_name"],
                            "priority": 3, "reasoning": "fallback"} for s in manifest.missing_sources]

    return {
        "artifact_ids": manifest.artifact_ids,
        "sources_used": list(manifest.artifacts_by_source.keys()),
        "coverage_score": manifest.coverage_score,
        "retrieval_log": result.retrieval_log + [
            {"action": "llm_search_strategy", "queries": strategy_log}
        ],
        "current_stage": "evidence_retrieval",
        "pipeline_log": state.get("pipeline_log", []) + [
            {"step": "evidence_retrieval", "status": "completed",
             "artifacts": manifest.total_artifacts,
             "coverage": manifest.coverage_score,
             "llm_queries_planned": len(strategy_log)}
        ],
    }
