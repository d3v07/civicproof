"""Unit tests for pipeline.py — routing functions, build_graph, feature flags."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

_WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker")
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

_SRC_INIT = os.path.join(_WORKER_DIR, "src", "__init__.py")
if not os.path.exists(_SRC_INIT):
    open(_SRC_INIT, "a").close()

from src.graph.pipeline import route_after_audit, route_after_entity_resolution  # noqa: E402


class TestRouteAfterEntityResolution:
    def test_returns_end_when_no_entity(self):
        state = {"primary_entity": None}
        assert route_after_entity_resolution(state) == "__end__"

    def test_returns_evidence_retrieval_when_entity_exists(self):
        state = {"primary_entity": {"entity_id": "ent-001"}}
        assert route_after_entity_resolution(state) == "evidence_retrieval"

    def test_returns_evidence_retrieval_when_entity_present(self):
        state = {}  # missing key entirely
        assert route_after_entity_resolution(state) == "__end__"


class TestRouteAfterAudit:
    def test_returns_end_when_approved(self):
        state = {"audit_approved": True, "retry_count": 0}
        assert route_after_audit(state) == "__end__"

    def test_returns_case_composer_when_not_approved_can_retry(self):
        state = {"audit_approved": False, "retry_count": 0}
        assert route_after_audit(state) == "case_composer"

    def test_returns_end_when_max_retries_reached(self):
        state = {"audit_approved": False, "retry_count": 2}
        assert route_after_audit(state) == "__end__"

    def test_returns_end_when_retry_count_exceeds_max(self):
        state = {"audit_approved": False, "retry_count": 5}
        assert route_after_audit(state) == "__end__"

    def test_missing_audit_approved_treated_as_false(self):
        state = {"retry_count": 0}
        assert route_after_audit(state) == "case_composer"

    def test_missing_retry_count_defaults_zero(self):
        state = {"audit_approved": False}
        assert route_after_audit(state) == "case_composer"


class TestBuildGraph:
    def _make_settings(self, graph_builder=False, anomaly_detector=False):
        settings = MagicMock()
        settings.ENABLE_GRAPH_BUILDER = graph_builder
        settings.ENABLE_ANOMALY_DETECTOR = anomaly_detector
        return settings

    def test_minimal_pipeline_no_optional_nodes(self):
        with patch("src.graph.pipeline.get_settings", return_value=self._make_settings()):
            from src.graph.pipeline import build_graph
            graph = build_graph()

        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "entity_resolver" in node_names
        assert "evidence_retrieval" in node_names
        assert "case_composer" in node_names
        assert "auditor_gate" in node_names
        assert "graph_builder" not in node_names
        assert "anomaly_detector" not in node_names

    def test_graph_builder_only(self):
        settings = self._make_settings(graph_builder=True)
        with patch("src.graph.pipeline.get_settings", return_value=settings):
            from src.graph.pipeline import build_graph
            graph = build_graph()

        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "graph_builder" in node_names
        assert "anomaly_detector" not in node_names

    def test_anomaly_detector_only(self):
        settings = self._make_settings(anomaly_detector=True)
        with patch("src.graph.pipeline.get_settings", return_value=settings):
            from src.graph.pipeline import build_graph
            graph = build_graph()

        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "anomaly_detector" in node_names
        assert "graph_builder" not in node_names

    def test_both_optional_nodes(self):
        settings = self._make_settings(
            graph_builder=True, anomaly_detector=True,
        )
        with patch("src.graph.pipeline.get_settings", return_value=settings):
            from src.graph.pipeline import build_graph
            graph = build_graph()

        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "graph_builder" in node_names
        assert "anomaly_detector" in node_names

    def test_full_6_node_pipeline_has_all_nodes(self):
        settings = self._make_settings(
            graph_builder=True, anomaly_detector=True,
        )
        with patch("src.graph.pipeline.get_settings", return_value=settings):
            from src.graph.pipeline import build_graph
            graph = build_graph()

        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        expected = {
            "entity_resolver", "evidence_retrieval",
            "graph_builder", "anomaly_detector",
            "case_composer", "auditor_gate",
        }
        # __start__ and __end__ are internal langgraph nodes
        assert expected.issubset(node_names)

    def test_full_pipeline_edge_order(self):
        settings = self._make_settings(
            graph_builder=True, anomaly_detector=True,
        )
        with patch("src.graph.pipeline.get_settings", return_value=settings):
            from src.graph.pipeline import build_graph
            graph = build_graph()

        compiled = graph.compile()
        graph_data = compiled.get_graph()
        edges = {(e.source, e.target) for e in graph_data.edges}
        # Verify the full chain
        assert ("evidence_retrieval", "graph_builder") in edges
        assert ("graph_builder", "anomaly_detector") in edges
        assert ("anomaly_detector", "case_composer") in edges
        assert ("case_composer", "auditor_gate") in edges

    def test_default_settings_now_enable_both(self):
        """With updated config defaults, both agents should be enabled."""
        from src.graph.pipeline import build_graph
        with patch("src.graph.pipeline.get_settings") as mock_get:
            settings = MagicMock()
            settings.ENABLE_GRAPH_BUILDER = True
            settings.ENABLE_ANOMALY_DETECTOR = True
            mock_get.return_value = settings
            graph = build_graph()

        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "graph_builder" in node_names
        assert "anomaly_detector" in node_names
