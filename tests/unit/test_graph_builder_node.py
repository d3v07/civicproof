"""Unit tests for graph_builder_node and anomaly_detector_node.

Tests Phase 2 nodes with mocked DB, LLM, and agent dependencies.
Same import pattern as test_graph_nodes.py.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()


def _mock_async_ctx(mock_db):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_entity_dict(**overrides):
    defaults = dict(
        entity_id="ent-001",
        canonical_name="ACME CORP",
        entity_type="vendor",
        confidence=0.95,
    )
    defaults.update(overrides)
    return defaults


# ── Stand-in dataclasses ─────────────────────────────────────────────────

@dataclass
class _GraphBuildResult:
    edges_added: int = 2
    total_edges: int = 5
    centrality_scores: dict[str, float] = field(default_factory=lambda: {"ent-001": 0.8})
    build_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _RiskSignal:
    signal_type: str = "sole_source_concentration"
    severity: str = "medium"
    score: float = 0.6
    description: str = "High sole-source concentration"
    evidence: dict[str, Any] = field(default_factory=dict)
    affected_entity_ids: list[str] = field(default_factory=list)
    supporting_artifact_ids: list[str] = field(default_factory=list)


@dataclass
class _AnomalyDetectionResult:
    risk_signals: list[_RiskSignal] = field(default_factory=list)
    composite_risk_score: float = 0.0
    detection_log: list[dict[str, Any]] = field(default_factory=list)


# ── Graph Builder Node ───────────────────────────────────────────────────

class TestGraphBuilderNode:
    @pytest.mark.asyncio
    async def test_returns_graph_result(self):
        build_result = _GraphBuildResult()
        mock_db = AsyncMock()
        mock_builder = AsyncMock()
        mock_builder.build = AsyncMock(return_value=build_result)

        # Mock DB for LLM artifact query — return empty (no artifacts for LLM)
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        with (
            patch("src.graph.nodes.graph_builder.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.graph_builder.GraphBuilderAgent", return_value=mock_builder),
            patch("src.graph.nodes.graph_builder.get_agent_llm") as mock_llm_factory,
        ):
            from src.graph.nodes.graph_builder import graph_builder_node
            result = await graph_builder_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "related_entities": [],
                "artifact_ids": ["a1"],
                "pipeline_log": [],
            })

        assert result["graph_result"]["edges_added"] == 2
        assert result["graph_result"]["total_edges"] == 5
        assert result["current_stage"] == "graph_builder"
        assert result["pipeline_log"][0]["step"] == "graph_builder"
        assert result["pipeline_log"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_no_artifacts_skips_llm(self):
        build_result = _GraphBuildResult(edges_added=0, total_edges=0)
        mock_db = AsyncMock()
        mock_builder = AsyncMock()
        mock_builder.build = AsyncMock(return_value=build_result)

        with (
            patch("src.graph.nodes.graph_builder.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.graph_builder.GraphBuilderAgent", return_value=mock_builder),
            patch("src.graph.nodes.graph_builder.get_agent_llm") as mock_llm_factory,
        ):
            from src.graph.nodes.graph_builder import graph_builder_node
            result = await graph_builder_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "related_entities": [],
                "artifact_ids": [],
                "pipeline_log": [],
            })

        mock_llm_factory.assert_not_called()
        assert result["graph_result"]["llm_relationships"] == []

    @pytest.mark.asyncio
    async def test_llm_extracts_relationships(self):
        build_result = _GraphBuildResult()
        mock_db = AsyncMock()
        mock_builder = AsyncMock()
        mock_builder.build = AsyncMock(return_value=build_result)

        # Mock artifact from DB
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "a1"
        mock_artifact.source = "usaspending"
        mock_artifact.metadata_ = {
            "title": "Contract Award for ACME CORP",
            "body": "Subcontractor: Small Biz LLC providing logistics support.",
        }

        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([mock_artifact]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='[{"source_entity": "ACME CORP", "target_entity": "Small Biz LLC", '
                    '"rel_type": "contractor_subcontractor", "evidence_excerpt": "Subcontractor: Small Biz LLC", '
                    '"confidence": 0.9}]'
        ))

        with (
            patch("src.graph.nodes.graph_builder.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.graph_builder.GraphBuilderAgent", return_value=mock_builder),
            patch("src.graph.nodes.graph_builder.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.graph_builder import graph_builder_node
            result = await graph_builder_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "related_entities": [],
                "artifact_ids": ["a1"],
                "pipeline_log": [],
            })

        assert len(result["graph_result"]["llm_relationships"]) == 1
        rel = result["graph_result"]["llm_relationships"][0]
        assert rel["rel_type"] == "contractor_subcontractor"
        assert rel["artifact_id"] == "a1"

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        build_result = _GraphBuildResult()
        mock_db = AsyncMock()
        mock_builder = AsyncMock()
        mock_builder.build = AsyncMock(return_value=build_result)

        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "a1"
        mock_artifact.source = "usaspending"
        mock_artifact.metadata_ = {"title": "Large contract for testing"}

        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([mock_artifact]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        with (
            patch("src.graph.nodes.graph_builder.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.graph_builder.GraphBuilderAgent", return_value=mock_builder),
            patch("src.graph.nodes.graph_builder.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.graph_builder import graph_builder_node
            result = await graph_builder_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "related_entities": [],
                "artifact_ids": ["a1"],
                "pipeline_log": [],
            })

        # LLM failure is caught, result still returned with co-occurrence graph
        assert result["graph_result"]["edges_added"] == 2
        assert result["graph_result"]["llm_relationships"] == []

    @pytest.mark.asyncio
    async def test_short_doc_text_skipped(self):
        build_result = _GraphBuildResult()
        mock_db = AsyncMock()
        mock_builder = AsyncMock()
        mock_builder.build = AsyncMock(return_value=build_result)

        # Artifact with very short metadata
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "a1"
        mock_artifact.source = "usaspending"
        mock_artifact.metadata_ = {"title": "X"}  # < 50 chars

        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([mock_artifact]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_llm = AsyncMock()

        with (
            patch("src.graph.nodes.graph_builder.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.graph_builder.GraphBuilderAgent", return_value=mock_builder),
            patch("src.graph.nodes.graph_builder.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.graph_builder import graph_builder_node
            result = await graph_builder_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "related_entities": [],
                "artifact_ids": ["a1"],
                "pipeline_log": [],
            })

        # LLM should NOT be invoked for short docs
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_preserves_pipeline_log(self):
        build_result = _GraphBuildResult()
        mock_db = AsyncMock()
        mock_builder = AsyncMock()
        mock_builder.build = AsyncMock(return_value=build_result)

        with (
            patch("src.graph.nodes.graph_builder.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.graph_builder.GraphBuilderAgent", return_value=mock_builder),
        ):
            from src.graph.nodes.graph_builder import graph_builder_node
            result = await graph_builder_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "related_entities": [],
                "artifact_ids": [],
                "pipeline_log": [{"step": "previous", "status": "ok"}],
            })

        assert len(result["pipeline_log"]) == 2
        assert result["pipeline_log"][0]["step"] == "previous"


# ── Anomaly Detector Node ────────────────────────────────────────────────

class TestAnomalyDetectorNode:
    @pytest.mark.asyncio
    async def test_returns_risk_signals(self):
        signal = _RiskSignal()
        detect_result = _AnomalyDetectionResult(
            risk_signals=[signal],
            composite_risk_score=0.3,
        )
        mock_db = AsyncMock()
        # Mock _build_awards_data DB call
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=detect_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='[{"hypothesis": "Possible sole-source pattern", "confidence": 0.5, '
                    '"supporting_signals": ["sole_source_concentration"], "reasoning": "test"}]'
        ))

        with (
            patch("src.graph.nodes.anomaly_detector.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.anomaly_detector.AnomalyDetectorAgent", return_value=mock_detector),
            patch("src.graph.nodes.anomaly_detector.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.anomaly_detector import anomaly_detector_node
            result = await anomaly_detector_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": ["a1"],
                "sources_used": ["usaspending"],
                "pipeline_log": [],
            })

        # 1 deterministic signal + 1 LLM hypothesis
        assert len(result["risk_signals"]) == 2
        assert result["risk_signals"][0]["signal_type"] == "sole_source_concentration"
        assert result["risk_signals"][1]["signal_type"] == "llm_hypothesis"
        assert result["composite_risk_score"] == 0.3
        assert result["current_stage"] == "anomaly_detector"

    @pytest.mark.asyncio
    async def test_no_signals_skips_llm(self):
        detect_result = _AnomalyDetectionResult(
            risk_signals=[],
            composite_risk_score=0.0,
        )
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=detect_result)

        with (
            patch("src.graph.nodes.anomaly_detector.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.anomaly_detector.AnomalyDetectorAgent", return_value=mock_detector),
            patch("src.graph.nodes.anomaly_detector.get_agent_llm") as mock_llm_factory,
        ):
            from src.graph.nodes.anomaly_detector import anomaly_detector_node
            result = await anomaly_detector_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": [],
                "sources_used": [],
                "pipeline_log": [],
            })

        mock_llm_factory.assert_not_called()
        assert result["risk_signals"] == []

    @pytest.mark.asyncio
    async def test_llm_failure_returns_deterministic_only(self):
        signal = _RiskSignal()
        detect_result = _AnomalyDetectionResult(
            risk_signals=[signal],
            composite_risk_score=0.3,
        )
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=detect_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))

        with (
            patch("src.graph.nodes.anomaly_detector.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.anomaly_detector.AnomalyDetectorAgent", return_value=mock_detector),
            patch("src.graph.nodes.anomaly_detector.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.anomaly_detector import anomaly_detector_node
            result = await anomaly_detector_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": ["a1"],
                "sources_used": ["usaspending"],
                "pipeline_log": [],
            })

        # Only deterministic signal, no LLM hypotheses
        assert len(result["risk_signals"]) == 1
        assert result["risk_signals"][0]["signal_type"] == "sole_source_concentration"

    @pytest.mark.asyncio
    async def test_high_confidence_hypothesis_is_high_severity(self):
        signal = _RiskSignal()
        detect_result = _AnomalyDetectionResult(
            risk_signals=[signal],
            composite_risk_score=0.5,
        )
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=detect_result)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(
            content='[{"hypothesis": "Strong bid rigging pattern", "confidence": 0.85, '
                    '"supporting_signals": ["sole_source_concentration"], "reasoning": "Strong correlation"}]'
        ))

        with (
            patch("src.graph.nodes.anomaly_detector.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.anomaly_detector.AnomalyDetectorAgent", return_value=mock_detector),
            patch("src.graph.nodes.anomaly_detector.get_agent_llm", return_value=mock_llm),
        ):
            from src.graph.nodes.anomaly_detector import anomaly_detector_node
            result = await anomaly_detector_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": ["a1"],
                "sources_used": ["usaspending"],
                "pipeline_log": [],
            })

        llm_signal = result["risk_signals"][1]
        assert llm_signal["severity"] == "high"
        assert llm_signal["score"] == 0.85

    @pytest.mark.asyncio
    async def test_preserves_pipeline_log(self):
        detect_result = _AnomalyDetectionResult(risk_signals=[], composite_risk_score=0.0)
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_detector = AsyncMock()
        mock_detector.detect = AsyncMock(return_value=detect_result)

        with (
            patch("src.graph.nodes.anomaly_detector.async_session_context", return_value=_mock_async_ctx(mock_db)),
            patch("src.agents.anomaly_detector.AnomalyDetectorAgent", return_value=mock_detector),
        ):
            from src.graph.nodes.anomaly_detector import anomaly_detector_node
            result = await anomaly_detector_node({
                "case_id": "c-1",
                "primary_entity": _make_entity_dict(),
                "artifact_ids": [],
                "sources_used": [],
                "pipeline_log": [{"step": "prev", "status": "ok"}],
            })

        assert len(result["pipeline_log"]) == 2
        assert result["pipeline_log"][0]["step"] == "prev"
        assert result["pipeline_log"][1]["step"] == "anomaly_detector"


# ── _build_awards_data helper ────────────────────────────────────────────

class TestBuildAwardsData:
    @pytest.mark.asyncio
    async def test_empty_artifact_ids(self):
        from src.graph.nodes.anomaly_detector import _build_awards_data
        mock_db = AsyncMock()
        result = await _build_awards_data(mock_db, [])
        assert result == []
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_builds_award_dicts(self):
        mock_artifact = MagicMock()
        mock_artifact.artifact_id = "a1"
        mock_artifact.metadata_ = {
            "vendor_id": "v1",
            "award_amount": 50000,
            "awarding_agency": "DOD",
            "start_date": "2025-01-01",
            "extent_competed": "full",
        }

        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars = MagicMock(return_value=iter([mock_artifact]))
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        from src.graph.nodes.anomaly_detector import _build_awards_data
        result = await _build_awards_data(mock_db, ["a1"])

        assert len(result) == 1
        assert result[0]["award_id"] == "a1"
        assert result[0]["award_amount"] == 50000
        assert result[0]["awarding_agency"] == "DOD"


# ── _format_risk_signals helper ──────────────────────────────────────────

class TestFormatRiskSignals:
    def test_empty_signals(self):
        from src.graph.nodes.anomaly_detector import _format_risk_signals
        assert "No risk signals" in _format_risk_signals([])

    def test_formats_signal(self):
        from src.graph.nodes.anomaly_detector import _format_risk_signals
        signal = _RiskSignal()
        text = _format_risk_signals([signal])
        assert "MEDIUM" in text
        assert "sole_source_concentration" in text
        assert "0.60" in text
