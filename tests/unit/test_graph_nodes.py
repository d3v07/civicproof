"""Unit tests for the 4 LangGraph node functions.

Each node is tested with mocked DB sessions and LLM calls.
Verifies state contracts: correct keys returned, pipeline_log appended.

Because node functions use relative imports (from ...agents), we must
import them via the proper package hierarchy (src.graph.nodes.*).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add services/worker to path so 'src' is a proper package
_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

# Also ensure src is importable as a package
_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()


# ── Lightweight stand-in dataclasses ──────────────────────────────────────

@dataclass
class _ResolvedEntity:
    entity_id: str = "ent-001"
    canonical_name: str = "ACME CORP"
    entity_type: str = "vendor"
    confidence: float = 0.95
    resolution_method: str = "fuzzy"
    uei: str | None = "ABC123"
    cage_code: str | None = "1A2B3"
    aliases: list[str] = field(default_factory=lambda: ["Acme Corporation"])
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _EntityResolutionResult:
    primary_entity: _ResolvedEntity | None = None
    related_entities: list[_ResolvedEntity] = field(default_factory=list)
    resolution_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _ArtifactManifest:
    entity_id: str = "ent-001"
    total_artifacts: int = 3
    artifacts_by_source: dict[str, int] = field(default_factory=lambda: {"usaspending": 3})
    stale_sources: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=lambda: ["doj", "sec_edgar", "oversight_gov"])
    artifact_ids: list[str] = field(default_factory=lambda: ["a1", "a2", "a3"])
    freshness: dict = field(default_factory=dict)
    coverage_score: float = 0.25


@dataclass
class _EvidenceRetrievalResult:
    manifest: _ArtifactManifest = field(default_factory=_ArtifactManifest)
    fetches_triggered: list[dict[str, Any]] = field(default_factory=list)
    retrieval_log: list[dict[str, Any]] = field(default_factory=list)


def _make_entity_dict(**overrides):
    defaults = dict(
        entity_id="ent-001",
        canonical_name="ACME CORP",
        entity_type="vendor",
        confidence=0.95,
        resolution_method="fuzzy",
        uei="ABC123",
        cage_code="1A2B3",
        aliases=["Acme Corporation"],
        metadata={},
    )
    defaults.update(overrides)
    return defaults


def _mock_async_ctx(mock_db):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ── Entity Resolver Node ──────────────────────────────────────────────────

class TestEntityResolverNode:
    @pytest.mark.asyncio
    async def test_returns_entity_on_success(self):
        entity = _ResolvedEntity()
        mock_result = _EntityResolutionResult(
            primary_entity=entity,
            related_entities=[],
            resolution_log=[{"tier": "fuzzy", "confidence": 0.95}],
        )
        mock_db = AsyncMock()
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_result)

        with (
            patch("src.graph.nodes.entity_resolver.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.entity_resolver.EntityResolverAgent", return_value=mock_resolver),
        ):
            from src.graph.nodes.entity_resolver import entity_resolver_node
            result = await entity_resolver_node({
                "case_id": "c-1",
                "seed_input": {"vendor_name": "Acme Corp"},
                "pipeline_log": [],
            })

        assert result["primary_entity"]["entity_id"] == "ent-001"
        assert result["primary_entity"]["canonical_name"] == "ACME CORP"
        assert result["current_stage"] == "entity_resolver"
        assert result["pipeline_log"][0]["step"] == "entity_resolver"
        assert result["pipeline_log"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_entity(self):
        mock_result = _EntityResolutionResult(
            primary_entity=None,
            resolution_log=[{"tier": "fuzzy", "status": "no_match"}],
        )
        mock_db = AsyncMock()
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_result)

        with (
            patch("src.graph.nodes.entity_resolver.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.entity_resolver.EntityResolverAgent", return_value=mock_resolver),
        ):
            from src.graph.nodes.entity_resolver import entity_resolver_node
            result = await entity_resolver_node({
                "case_id": "c-1",
                "seed_input": {"vendor_name": "NonExistent"},
                "pipeline_log": [],
            })

        assert result["primary_entity"] is None
        assert result["related_entities"] == []
        assert result["pipeline_log"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_llm_skipped_when_high_confidence_no_related(self):
        entity = _ResolvedEntity(confidence=0.95)
        mock_result = _EntityResolutionResult(
            primary_entity=entity, related_entities=[], resolution_log=[],
        )
        mock_db = AsyncMock()
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_result)

        with (
            patch("src.graph.nodes.entity_resolver.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.entity_resolver.EntityResolverAgent", return_value=mock_resolver),
            patch("src.graph.nodes.entity_resolver.get_agent_llm") as mock_llm_factory,
        ):
            from src.graph.nodes.entity_resolver import entity_resolver_node
            result = await entity_resolver_node({
                "case_id": "c-1",
                "seed_input": {"vendor_name": "Acme Corp"},
                "pipeline_log": [],
            })

        mock_llm_factory.assert_not_called()
        assert result["primary_entity"]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_llm_disambiguation_runs_on_low_confidence(self):
        entity = _ResolvedEntity(confidence=0.6)
        related = _ResolvedEntity(entity_id="ent-002", canonical_name="ACME INC")
        mock_result = _EntityResolutionResult(
            primary_entity=entity, related_entities=[related], resolution_log=[],
        )
        mock_db = AsyncMock()
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"entity_id": "ent-001", "canonical_name": "ACME CORP", '
                    '"confidence": 0.85, "reasoning": "matched UEI", "merged_aliases": ["Acme Inc"]}'
        ))

        with (
            patch("src.graph.nodes.entity_resolver.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.entity_resolver.EntityResolverAgent", return_value=mock_resolver),
            patch("src.graph.nodes.entity_resolver.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.entity_resolver import entity_resolver_node
            result = await entity_resolver_node({
                "case_id": "c-1",
                "seed_input": {"vendor_name": "Acme"},
                "pipeline_log": [],
            })

        assert result["primary_entity"]["confidence"] == 0.85
        assert result["primary_entity"]["resolution_method"] == "llm"
        assert "Acme Inc" in result["primary_entity"]["aliases"]

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_gracefully(self):
        entity = _ResolvedEntity(confidence=0.6)
        related = _ResolvedEntity(entity_id="ent-002")
        mock_result = _EntityResolutionResult(
            primary_entity=entity, related_entities=[related], resolution_log=[],
        )
        mock_db = AsyncMock()
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with (
            patch("src.graph.nodes.entity_resolver.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.entity_resolver.EntityResolverAgent", return_value=mock_resolver),
            patch("src.graph.nodes.entity_resolver.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.entity_resolver import entity_resolver_node
            result = await entity_resolver_node({
                "case_id": "c-1",
                "seed_input": {"vendor_name": "Acme"},
                "pipeline_log": [],
            })

        assert result["primary_entity"]["confidence"] == 0.6
        assert result["primary_entity"]["resolution_method"] == "fuzzy"


# ── Evidence Retrieval Node ───────────────────────────────────────────────

class TestEvidenceRetrievalNode:
    @pytest.mark.asyncio
    async def test_returns_manifest_on_success(self):
        manifest = _ArtifactManifest()
        mock_result = _EvidenceRetrievalResult(
            manifest=manifest,
            retrieval_log=[{"action": "gap_identified", "missing_sources": ["doj"]}],
        )
        mock_db = AsyncMock()
        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(return_value=mock_result)

        with (
            patch("src.graph.nodes.evidence_retrieval.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.evidence_retrieval.EvidenceRetrievalAgent", return_value=mock_retriever),
        ):
            from src.graph.nodes.evidence_retrieval import evidence_retrieval_node
            result = await evidence_retrieval_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "pipeline_log": [],
            })

        assert result["artifact_ids"] == ["a1", "a2", "a3"]
        assert "usaspending" in result["sources_used"]
        assert result["coverage_score"] == 0.25
        assert result["current_stage"] == "evidence_retrieval"
        assert result["pipeline_log"][0]["step"] == "evidence_retrieval"

    @pytest.mark.asyncio
    async def test_llm_strategy_skipped_when_no_gaps(self):
        manifest = _ArtifactManifest(missing_sources=[], stale_sources=[])
        mock_result = _EvidenceRetrievalResult(manifest=manifest, retrieval_log=[])
        mock_db = AsyncMock()
        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(return_value=mock_result)

        with (
            patch("src.graph.nodes.evidence_retrieval.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.evidence_retrieval.EvidenceRetrievalAgent", return_value=mock_retriever),
            patch("src.graph.nodes.evidence_retrieval.get_agent_llm") as mock_llm_factory,
        ):
            from src.graph.nodes.evidence_retrieval import evidence_retrieval_node
            result = await evidence_retrieval_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "pipeline_log": [],
            })

        mock_llm_factory.assert_not_called()
        assert result["pipeline_log"][0]["llm_queries_planned"] == 0

    @pytest.mark.asyncio
    async def test_llm_strategy_runs_when_gaps_exist(self):
        manifest = _ArtifactManifest(missing_sources=["doj", "sec_edgar"])
        mock_result = _EvidenceRetrievalResult(manifest=manifest, retrieval_log=[])
        mock_db = AsyncMock()
        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(return_value=mock_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='[{"source": "doj", "query": "ACME fraud", "priority": 4, "reasoning": "test"}]'
        ))

        with (
            patch("src.graph.nodes.evidence_retrieval.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.evidence_retrieval.EvidenceRetrievalAgent", return_value=mock_retriever),
            patch("src.graph.nodes.evidence_retrieval.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.evidence_retrieval import evidence_retrieval_node
            result = await evidence_retrieval_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "pipeline_log": [],
            })

        assert result["pipeline_log"][0]["llm_queries_planned"] == 1

    @pytest.mark.asyncio
    async def test_llm_strategy_failure_uses_fallback(self):
        manifest = _ArtifactManifest(missing_sources=["doj"])
        mock_result = _EvidenceRetrievalResult(manifest=manifest, retrieval_log=[])
        mock_db = AsyncMock()
        mock_retriever = AsyncMock()
        mock_retriever.retrieve = AsyncMock(return_value=mock_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))

        with (
            patch("src.graph.nodes.evidence_retrieval.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.evidence_retrieval.EvidenceRetrievalAgent", return_value=mock_retriever),
            patch("src.graph.nodes.evidence_retrieval.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.evidence_retrieval import evidence_retrieval_node
            result = await evidence_retrieval_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "pipeline_log": [],
            })

        assert result["pipeline_log"][0]["llm_queries_planned"] == 1


# ── Case Composer Node ───────────────────────────────────────────────────

class TestCaseComposerNode:
    @pytest.mark.asyncio
    async def test_returns_case_pack_with_llm_title(self):
        mock_pack = MagicMock()
        mock_pack.case_id = "c-1"
        mock_pack.title = "Deterministic Title"
        mock_pack.summary = "Deterministic summary"
        mock_claim = MagicMock()
        mock_claim.claim_id = "cl-1"
        mock_claim.statement = "Entity received awards."
        mock_claim.claim_type = "finding"
        mock_claim.confidence = 1.0
        mock_claim.citation_ids = ["a1"]
        mock_claim.artifact_ids = ["a1"]
        mock_pack.claims = [mock_claim]
        mock_pack.risk_signals = []
        mock_pack.entity_profile = _make_entity_dict()
        mock_pack.evidence_summary = {"total_artifacts": 3}
        mock_pack.timeline = []
        mock_pack.sources_used = ["usaspending"]
        mock_pack.pack_hash = "abc123"
        mock_pack.compute_hash = MagicMock(return_value="newhash")

        mock_composition = MagicMock()
        mock_composition.case_pack = mock_pack

        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='{"title": "LLM Title", "summary": "LLM summary.", "hypotheses": []}'
        ))

        with (
            patch("src.graph.nodes.case_composer.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.graph.nodes.case_composer.get_agent_llm", return_value=mock_llm),
            patch("src.agents.case_composer.CaseComposerAgent") as MockComposer,
            patch("src.graph.nodes.anomaly_detector._build_awards_data", new_callable=AsyncMock, return_value=[]),
        ):
            MockComposer.return_value.compose = MagicMock(return_value=mock_composition)
            MockComposer.return_value._deterministic_claim_id = MagicMock(return_value="det-id")
            from src.graph.nodes.case_composer import case_composer_node
            result = await case_composer_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": ["a1", "a2"],
                "sources_used": ["usaspending"],
                "risk_signals": [],
                "pipeline_log": [],
            })

        assert result["case_pack"]["title"] == "LLM Title"
        assert result["current_stage"] == "case_composer"
        assert result["pipeline_log"][0]["step"] == "case_composer"

    @pytest.mark.asyncio
    async def test_llm_failure_uses_deterministic_output(self):
        mock_pack = MagicMock()
        mock_pack.case_id = "c-1"
        mock_pack.title = "Deterministic Title"
        mock_pack.summary = "Deterministic summary"
        mock_pack.claims = []
        mock_pack.risk_signals = []
        mock_pack.entity_profile = _make_entity_dict()
        mock_pack.evidence_summary = {}
        mock_pack.timeline = []
        mock_pack.sources_used = ["usaspending"]
        mock_pack.pack_hash = "def456"

        mock_composition = MagicMock()
        mock_composition.case_pack = mock_pack

        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("src.graph.nodes.case_composer.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.graph.nodes.case_composer.get_agent_llm", return_value=mock_llm),
            patch("src.agents.case_composer.CaseComposerAgent") as MockComposer,
            patch("src.graph.nodes.anomaly_detector._build_awards_data", new_callable=AsyncMock, return_value=[]),
        ):
            MockComposer.return_value.compose = MagicMock(return_value=mock_composition)
            from src.graph.nodes.case_composer import case_composer_node
            result = await case_composer_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": ["a1"],
                "sources_used": ["usaspending"],
                "risk_signals": [],
                "pipeline_log": [],
            })

        assert result["case_pack"]["title"] == "Deterministic Title"
        assert result["case_pack"]["summary"] == "Deterministic summary"


# ── Auditor Gate Node ─────────────────────────────────────────────────────

class TestAuditorGateNode:
    @pytest.mark.asyncio
    async def test_approved_case_pack(self):
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_audit_result = MagicMock()
        mock_audit_result.approved = True
        mock_audit_result.violations = []
        mock_audit_result.summary = "APPROVED"

        with (
            patch("src.graph.nodes.auditor_gate.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.auditor.AuditorGate") as MockGate,
        ):
            MockGate.return_value.audit = MagicMock(return_value=mock_audit_result)
            from src.graph.nodes.auditor_gate import auditor_gate_node
            result = await auditor_gate_node({
                "case_pack": {
                    "claims": [{"claim_id": "c1", "statement": "Risk signal.",
                                "claim_type": "risk_signal", "confidence": 0.7,
                                "citation_ids": [], "artifact_ids": []}],
                    "sources_used": ["usaspending"],
                    "summary": "Test", "title": "Test",
                },
                "artifact_ids": [],
                "pipeline_log": [],
            })

        assert result["audit_approved"] is True
        assert result["audit_result"]["approved"] is True
        assert result["current_stage"] == "auditor_gate"
        assert result["pipeline_log"][0]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_blocked_case_pack_increments_retry(self):
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_audit_result = MagicMock()
        mock_audit_result.approved = False
        mock_audit_result.violations = ["CITATION_REQUIRED: no citation", "ACCUSATORY: banned"]
        mock_audit_result.summary = "BLOCKED"

        with (
            patch("src.graph.nodes.auditor_gate.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.auditor.AuditorGate") as MockGate,
        ):
            MockGate.return_value.audit = MagicMock(return_value=mock_audit_result)
            from src.graph.nodes.auditor_gate import auditor_gate_node
            result = await auditor_gate_node({
                "case_pack": {
                    "claims": [], "sources_used": ["usaspending"],
                    "summary": "Test", "title": "Test",
                },
                "artifact_ids": [],
                "retry_count": 0,
                "pipeline_log": [],
            })

        assert result["audit_approved"] is False
        assert result["retry_count"] == 1
        assert len(result["audit_result"]["violations"]) > 0
        assert result["pipeline_log"][0]["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_artifact_hashes_passed_to_auditor(self):
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "a1"
        mock_artifact.content_hash = "hash123"

        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([mock_artifact]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_audit_result = MagicMock()
        mock_audit_result.approved = True
        mock_audit_result.violations = []
        mock_audit_result.summary = "APPROVED"

        with (
            patch("src.graph.nodes.auditor_gate.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.auditor.AuditorGate") as MockGate,
        ):
            MockGate.return_value.audit = MagicMock(return_value=mock_audit_result)
            from src.graph.nodes.auditor_gate import auditor_gate_node
            result = await auditor_gate_node({
                "case_pack": {
                    "claims": [{"claim_id": "c1", "statement": "$5M awards.",
                                "claim_type": "finding", "confidence": 1.0,
                                "citation_ids": ["a1"], "artifact_ids": ["a1"]}],
                    "sources_used": ["usaspending"],
                    "summary": "Test", "title": "Test",
                },
                "artifact_ids": ["a1"],
                "pipeline_log": [],
            })

        assert result["audit_approved"] is True
        # Verify AuditorGate was called with correct artifact_hashes
        call_kwargs = MockGate.call_args[1]
        assert call_kwargs["artifact_hashes"] == {"a1": "hash123"}


# ── Pipeline Log Contracts ────────────────────────────────────────────────

class TestPipelineLogContract:
    @pytest.mark.asyncio
    async def test_entity_resolver_preserves_existing_log(self):
        entity = _ResolvedEntity()
        mock_result = _EntityResolutionResult(primary_entity=entity)
        mock_db = AsyncMock()
        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_result)

        with (
            patch("src.graph.nodes.entity_resolver.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.entity_resolver.EntityResolverAgent", return_value=mock_resolver),
        ):
            from src.graph.nodes.entity_resolver import entity_resolver_node
            result = await entity_resolver_node({
                "case_id": "c-1",
                "seed_input": {"vendor_name": "Test"},
                "pipeline_log": [{"step": "init", "status": "ok"}],
            })

        assert len(result["pipeline_log"]) == 2
        assert result["pipeline_log"][0] == {"step": "init", "status": "ok"}
        assert result["pipeline_log"][1]["step"] == "entity_resolver"

    @pytest.mark.asyncio
    async def test_auditor_gate_preserves_existing_log(self):
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_audit_result = MagicMock()
        mock_audit_result.approved = True
        mock_audit_result.violations = []
        mock_audit_result.summary = "APPROVED"

        with (
            patch("src.graph.nodes.auditor_gate.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.auditor.AuditorGate") as MockGate,
        ):
            MockGate.return_value.audit = MagicMock(return_value=mock_audit_result)
            from src.graph.nodes.auditor_gate import auditor_gate_node
            result = await auditor_gate_node({
                "case_pack": {
                    "claims": [], "sources_used": ["usaspending"],
                    "summary": "Test", "title": "Test",
                },
                "artifact_ids": [],
                "pipeline_log": [{"step": "previous", "status": "ok"}],
            })

        assert len(result["pipeline_log"]) == 2
        assert result["pipeline_log"][0]["step"] == "previous"
        assert result["pipeline_log"][1]["step"] == "auditor_gate"
