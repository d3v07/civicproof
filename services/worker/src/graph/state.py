"""CivicProof LangGraph state definition."""

from __future__ import annotations

from typing import Any, TypedDict


class CivicProofState(TypedDict, total=False):
    """Shared state flowing through the 6-agent LangGraph pipeline.

    Keys are incrementally populated by each node. TypedDict(total=False)
    allows nodes to omit keys they don't own.
    """

    # ── Seed ─────────────────────────────────────────────
    case_id: str
    seed_input: dict[str, Any]

    # ── Entity Resolver output ───────────────────────────
    primary_entity: dict[str, Any] | None
    related_entities: list[dict[str, Any]]
    resolution_log: list[dict[str, Any]]

    # ── Evidence Retrieval output ──────────────────────
    artifact_ids: list[str]
    sources_used: list[str]
    coverage_score: float
    retrieval_log: list[dict[str, Any]]

    # ── Graph Builder output ─────────────────────────────
    graph_result: dict[str, Any]

    # ── Anomaly Detector output ──────────────────────────
    risk_signals: list[dict[str, Any]]
    composite_risk_score: float

    # ── Case Composer output ─────────────────────────────
    case_pack: dict[str, Any]
    claims: list[dict[str, Any]]

    # ── Auditor Gate output ──────────────────────────────
    audit_result: dict[str, Any]
    audit_approved: bool

    # ── Pipeline control ─────────────────────────────────
    current_stage: str
    retry_count: int
    pipeline_log: list[dict[str, Any]]
    error: str | None
