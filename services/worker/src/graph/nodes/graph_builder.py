"""Graph Builder node — existing co-occurrence + LLM relationship extraction."""

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
    "You are a relationship extraction specialist for federal procurement investigations. "
    "Extract entity relationships from government documents.\n\n"
    "Relationship types: contractor_subcontractor, officer_of, subsidiary_of, "
    "shared_address, political_donor, awarded_by, lobbied_by, audited_by.\n\n"
    "Rules:\n"
    "- Only extract relationships explicitly stated or strongly implied in the text\n"
    "- Never infer relationships not supported by the document\n"
    "- Cite the exact excerpt supporting each relationship\n"
    "- Confidence 0.9+ only for explicitly stated relationships\n"
    "Return ONLY valid JSON — no markdown fences."
)

MAX_DOCS_FOR_LLM = 15
MAX_DOC_CHARS = 4000


async def graph_builder_node(state: CivicProofState) -> dict[str, Any]:
    from ...agents.graph_builder import GraphBuilderAgent

    entity = state["primary_entity"]
    related = state.get("related_entities", [])
    artifact_ids = state.get("artifact_ids", [])

    all_entity_ids = [entity["entity_id"]] + [e["entity_id"] for e in related]
    entity_names = [entity["canonical_name"]] + [e.get("canonical_name", "") for e in related]

    # Step 1: Existing co-occurrence graph (always runs)
    async with async_session_context() as db:
        builder = GraphBuilderAgent(db)
        result = await builder.build(all_entity_ids, artifact_ids)

    llm_relationships = []

    # Step 2: LLM-enhanced relationship extraction from parsed documents
    if artifact_ids:
        try:
            llm = get_agent_llm("graph_builder", temperature=0.1, max_tokens=2048, case_id=state.get("case_id", ""))

            async with async_session_context() as db:
                from civicproof_common.db.models import RawArtifactModel
                from sqlalchemy import select

                stmt = (
                    select(RawArtifactModel)
                    .where(RawArtifactModel.artifact_id.in_(artifact_ids[:MAX_DOCS_FOR_LLM]))
                )
                db_result = await db.execute(stmt)
                artifacts = list(db_result.scalars())

            for art in artifacts:
                doc_text = ""
                meta = art.metadata_ or {}
                # Build readable text from metadata fields
                for key in ("title", "body", "summary", "description", "recipient_name"):
                    val = meta.get(key, "")
                    if val:
                        doc_text += f"{key}: {val}\n"
                if not doc_text.strip():
                    doc_text = json.dumps(meta, default=str)

                doc_text = doc_text[:MAX_DOC_CHARS]
                if len(doc_text) < 50:
                    continue

                prompt = (
                    f"From this federal document (source: {art.source}), extract entity relationships:\n\n"
                    f"{doc_text}\n\n"
                    f"Known entities in this case: {entity_names}\n\n"
                    "Return JSON array of relationships:\n"
                    '[{"source_entity": "...", "target_entity": "...", '
                    '"rel_type": "contractor_subcontractor|officer_of|subsidiary_of|shared_address|political_donor|awarded_by", '
                    '"evidence_excerpt": "...", "confidence": 0.0-1.0}]\n\n'
                    "Return [] if no relationships found."
                )
                response = await llm.ainvoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
                try:
                    rels = json.loads(response.content)
                    if isinstance(rels, list):
                        for rel in rels:
                            rel["artifact_id"] = art.artifact_id
                        llm_relationships.extend(rels)
                except (json.JSONDecodeError, TypeError):
                    pass

            logger.info(
                "LLM extracted %d relationships from %d documents",
                len(llm_relationships), len(artifacts),
            )
        except Exception as exc:
            logger.warning("LLM relationship extraction failed: %s", exc)

    return {
        "graph_result": {
            "edges_added": result.edges_added,
            "total_edges": result.total_edges,
            "centrality_scores": result.centrality_scores,
            "llm_relationships": llm_relationships,
        },
        "current_stage": "graph_builder",
        "pipeline_log": state.get("pipeline_log", []) + [
            {"step": "graph_builder", "status": "completed",
             "edges": result.total_edges,
             "llm_relationships": len(llm_relationships)}
        ],
    }
