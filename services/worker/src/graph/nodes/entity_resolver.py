"""Entity Resolver node — wraps existing agent + LLM Tier 3 disambiguation."""

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
    "You are an entity disambiguation specialist for federal procurement investigations. "
    "Vendor names have variations: Inc vs LLC, abbreviations, DBA names. "
    "Cross-reference UEI, CAGE, and DUNS identifiers. "
    "Return ONLY valid JSON — no markdown fences, no commentary."
)


def _entity_to_dict(entity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "canonical_name": entity.canonical_name,
        "entity_type": entity.entity_type,
        "confidence": entity.confidence,
        "resolution_method": entity.resolution_method,
        "uei": entity.uei,
        "cage_code": entity.cage_code,
        "aliases": entity.aliases,
        "metadata": getattr(entity, "metadata", {}),
    }


def _format_candidates(result) -> str:
    parts = []
    if result.primary_entity:
        e = result.primary_entity
        parts.append(
            f"- {e.canonical_name} (confidence={e.confidence}, method={e.resolution_method},"
            f" uei={e.uei}, cage={e.cage_code})"
        )
    for e in result.related_entities:
        parts.append(
            f"- {e.canonical_name} (confidence={e.confidence}, uei={e.uei})"
        )
    return "\n".join(parts) or "(none)"


async def entity_resolver_node(state: CivicProofState) -> dict[str, Any]:
    from ...agents.entity_resolver import EntityResolverAgent

    seed_input = state["seed_input"]

    async with async_session_context() as db:
        resolver = EntityResolverAgent(db)
        result = await resolver.resolve(seed_input)

    if result.primary_entity is None:
        return {
            "primary_entity": None,
            "related_entities": [],
            "resolution_log": result.resolution_log,
            "current_stage": "entity_resolver",
            "pipeline_log": state.get("pipeline_log", []) + [
                {"step": "entity_resolver", "status": "failed", "detail": "no entity found"}
            ],
        }

    entity = result.primary_entity

    # Tier 3: LLM disambiguation when confidence < 0.8 or tip_text present
    has_tip = bool(seed_input.get("tip_text"))
    needs_disambiguation = entity.confidence < 0.8 or has_tip

    if needs_disambiguation and len(result.related_entities) > 0:
        try:
            llm = get_agent_llm(
                "entity_resolver", temperature=0.1,
                case_id=state.get("case_id", ""),
            )
            prompt = (
                f"Given these candidate entities from federal databases:\n"
                f"{_format_candidates(result)}\n\n"
                f"And this seed input: {json.dumps(
                    {k: v for k, v in seed_input.items() if k != 'tip_text'}
                )}\n"
            )
            if has_tip:
                prompt += f"Tip text: {seed_input['tip_text'][:500]}\n"
            prompt += (
                "\nWhich entity is the correct match? If multiple, identify the primary entity "
                "and any aliases. Return JSON with:\n"
                '{"entity_id": "...", "canonical_name": "...", "confidence": 0.0-1.0, '
                '"reasoning": "...", "merged_aliases": ["..."]}'
            )
            response = await llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            llm_output = json.loads(response.content)
            if llm_output.get("confidence", 0) > entity.confidence:
                entity.confidence = min(llm_output["confidence"], 0.9)
                entity.resolution_method = "llm"
                if llm_output.get("merged_aliases"):
                    entity.aliases = list(set(entity.aliases + llm_output["merged_aliases"]))
            result.resolution_log.append({
                "tier": "llm_disambiguation",
                "llm_confidence": llm_output.get("confidence"),
                "reasoning": llm_output.get("reasoning", ""),
            })
        except Exception as exc:
            logger.warning("LLM disambiguation failed, using fuzzy result: %s", exc)
            result.resolution_log.append({
                "tier": "llm_disambiguation",
                "status": "failed",
                "error": str(exc),
            })

    return {
        "primary_entity": _entity_to_dict(entity),
        "related_entities": [_entity_to_dict(e) for e in result.related_entities],
        "resolution_log": result.resolution_log,
        "current_stage": "entity_resolver",
        "pipeline_log": state.get("pipeline_log", []) + [
            {"step": "entity_resolver", "status": "completed",
             "entity": entity.canonical_name, "confidence": entity.confidence}
        ],
    }
