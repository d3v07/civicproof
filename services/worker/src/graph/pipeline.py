"""LangGraph StateGraph pipeline — replaces Orchestrator.run_pipeline().

6-node pipeline with feature flags for graph_builder and anomaly_detector.
Minimum viable path: entity_resolver → evidence_retrieval → case_composer → auditor_gate
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
    settings = get_settings()
    builder = StateGraph(CivicProofState)

    builder.add_node("entity_resolver", entity_resolver_node)
    builder.add_node("evidence_retrieval", evidence_retrieval_node)
    builder.add_node("case_composer", case_composer_node)
    builder.add_node("auditor_gate", auditor_gate_node)

    builder.set_entry_point("entity_resolver")

    builder.add_conditional_edges(
        "entity_resolver",
        route_after_entity_resolution,
        {"evidence_retrieval": "evidence_retrieval", END: END},
    )

    if settings.ENABLE_GRAPH_BUILDER and settings.ENABLE_ANOMALY_DETECTOR:
        builder.add_node("graph_builder", graph_builder_node)
        builder.add_node("anomaly_detector", anomaly_detector_node)
        builder.add_edge("evidence_retrieval", "graph_builder")
        builder.add_edge("graph_builder", "anomaly_detector")
        builder.add_edge("anomaly_detector", "case_composer")
    elif settings.ENABLE_GRAPH_BUILDER:
        builder.add_node("graph_builder", graph_builder_node)
        builder.add_edge("evidence_retrieval", "graph_builder")
        builder.add_edge("graph_builder", "case_composer")
    elif settings.ENABLE_ANOMALY_DETECTOR:
        builder.add_node("anomaly_detector", anomaly_detector_node)
        builder.add_edge("evidence_retrieval", "anomaly_detector")
        builder.add_edge("anomaly_detector", "case_composer")
    else:
        builder.add_edge("evidence_retrieval", "case_composer")

    builder.add_edge("case_composer", "auditor_gate")
    builder.add_conditional_edges(
        "auditor_gate",
        route_after_audit,
        {"case_composer": "case_composer", END: END},
    )

    return builder


@lru_cache(maxsize=1)
def get_compiled_graph():
    builder = build_graph()
    return builder.compile()
