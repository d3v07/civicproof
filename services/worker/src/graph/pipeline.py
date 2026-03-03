"""LangGraph StateGraph pipeline — replaces Orchestrator.run_pipeline().

6-node linear pipeline with two conditional exits:
  1. entity_resolver → (no entity? END) → evidence_retrieval
  2. evidence_retrieval → graph_builder → anomaly_detector → case_composer
  3. case_composer → auditor_gate → (approved? END : retry case_composer, max 2)
"""

from __future__ import annotations

from functools import lru_cache

from civicproof_common.config import get_settings
from langgraph.graph import END, StateGraph

from .nodes import (
    anomaly_detector_node,
    auditor_gate_node,
    case_composer_node,
    entity_resolver_node,
    evidence_retrieval_node,
    graph_builder_node,
)
from .state import CivicProofState


def route_after_entity_resolution(state: CivicProofState) -> str:
    if state.get("primary_entity") is None:
        return END
    return "evidence_retrieval"


def route_after_audit(state: CivicProofState) -> str:
    if state.get("audit_approved"):
        return END
    retry = state.get("retry_count", 0)
    if retry >= 2:
        return END
    return "case_composer"


def build_graph() -> StateGraph:
    builder = StateGraph(CivicProofState)

    builder.add_node("entity_resolver", entity_resolver_node)
    builder.add_node("evidence_retrieval", evidence_retrieval_node)
    builder.add_node("graph_builder", graph_builder_node)
    builder.add_node("anomaly_detector", anomaly_detector_node)
    builder.add_node("case_composer", case_composer_node)
    builder.add_node("auditor_gate", auditor_gate_node)

    builder.set_entry_point("entity_resolver")

    builder.add_conditional_edges(
        "entity_resolver",
        route_after_entity_resolution,
        {"evidence_retrieval": "evidence_retrieval", END: END},
    )
    builder.add_edge("evidence_retrieval", "graph_builder")
    builder.add_edge("graph_builder", "anomaly_detector")
    builder.add_edge("anomaly_detector", "case_composer")
    builder.add_edge("case_composer", "auditor_gate")
    builder.add_conditional_edges(
        "auditor_gate",
        route_after_audit,
        {"case_composer": "case_composer", END: END},
    )

    return builder


@lru_cache(maxsize=1)
def get_compiled_graph():
    settings = get_settings()
    builder = build_graph()
    return builder.compile(
        recursion_limit=settings.LANGGRAPH_RECURSION_LIMIT,
    )
