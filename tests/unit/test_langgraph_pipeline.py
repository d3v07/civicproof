"""Tests for the LangGraph pipeline — routing, state, node contracts."""
from __future__ import annotations

import os
import sys

import pytest

_WORKER_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "services", "worker", "src")
if _WORKER_SRC not in sys.path:
    sys.path.insert(0, _WORKER_SRC)

from graph.state import CivicProofState
from graph.pipeline import route_after_entity_resolution, route_after_audit


# ── Routing functions ────────────────────────────────────────────────────────

class TestRouteAfterEntityResolution:
    def test_returns_end_when_no_entity(self):
        state: CivicProofState = {"primary_entity": None}  # type: ignore[typeddict-item]
        assert route_after_entity_resolution(state) == "__end__"

    def test_returns_evidence_retrieval_when_entity_present(self):
        state: CivicProofState = {
            "primary_entity": {"entity_id": "e1", "canonical_name": "ACME"}
        }  # type: ignore[typeddict-item]
        assert route_after_entity_resolution(state) == "evidence_retrieval"

    def test_returns_end_when_entity_key_missing(self):
        state: CivicProofState = {}  # type: ignore[typeddict-item]
        assert route_after_entity_resolution(state) == "__end__"


class TestRouteAfterAudit:
    def test_returns_end_when_approved(self):
        state: CivicProofState = {"audit_approved": True, "retry_count": 0}  # type: ignore[typeddict-item]
        assert route_after_audit(state) == "__end__"

    def test_returns_case_composer_on_first_failure(self):
        state: CivicProofState = {"audit_approved": False, "retry_count": 0}  # type: ignore[typeddict-item]
        assert route_after_audit(state) == "case_composer"

    def test_returns_case_composer_on_second_failure(self):
        state: CivicProofState = {"audit_approved": False, "retry_count": 1}  # type: ignore[typeddict-item]
        assert route_after_audit(state) == "case_composer"

    def test_returns_end_after_max_retries(self):
        state: CivicProofState = {"audit_approved": False, "retry_count": 2}  # type: ignore[typeddict-item]
        assert route_after_audit(state) == "__end__"

    def test_returns_end_when_no_approval_key(self):
        state: CivicProofState = {"retry_count": 3}  # type: ignore[typeddict-item]
        assert route_after_audit(state) == "__end__"


# ── State shape ──────────────────────────────────────────────────────────────

class TestCivicProofState:
    def test_state_is_total_false(self):
        state: CivicProofState = {}  # type: ignore[typeddict-item]
        assert state.get("case_id") is None
        assert state.get("primary_entity") is None
        assert state.get("retry_count") is None

    def test_state_accepts_seed_fields(self):
        state: CivicProofState = {
            "case_id": "c-123",
            "seed_input": {"vendor_name": "ACME"},
            "retry_count": 0,
            "pipeline_log": [],
        }  # type: ignore[typeddict-item]
        assert state["case_id"] == "c-123"
        assert state["seed_input"]["vendor_name"] == "ACME"

    def test_state_accepts_all_pipeline_outputs(self):
        state: CivicProofState = {
            "case_id": "c-1",
            "seed_input": {},
            "primary_entity": {"entity_id": "e1"},
            "related_entities": [],
            "artifact_ids": ["a1", "a2"],
            "sources_used": ["usaspending"],
            "risk_signals": [{"signal_type": "sole_source", "score": 0.8}],
            "composite_risk_score": 0.6,
            "case_pack": {"title": "Test"},
            "claims": [],
            "audit_approved": True,
            "audit_result": {"approved": True},
            "retry_count": 0,
            "pipeline_log": [],
        }  # type: ignore[typeddict-item]
        assert state["audit_approved"] is True
        assert len(state["artifact_ids"]) == 2


# ── LLM factory ─────────────────────────────────────────────────────────────

class TestLLMFactory:
    def test_get_llm_returns_chat_openai(self):
        """Verify factory produces a ChatOpenAI pointed at OpenRouter."""
        try:
            from graph.llm import get_llm
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-14b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_llm(temperature=0.3)
                assert llm.model_name == "qwen/qwen-2.5-72b-instruct"
                assert llm.openai_api_base == "https://openrouter.ai/api/v1"
        except ImportError:
            pytest.skip("langchain-openai not installed")

    def test_model_override(self):
        try:
            from graph.llm import get_llm
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_llm(model_override="qwen/qwen3-30b-a3b")
                assert llm.model_name == "qwen/qwen3-30b-a3b"
        except ImportError:
            pytest.skip("langchain-openai not installed")


# ── Phase 2: @tool wrappers ─────────────────────────────────────────────────

class TestToolWrappers:
    def test_all_tools_are_langchain_tools(self):
        from graph.tools import ALL_TOOLS
        from langchain_core.tools import BaseTool

        assert len(ALL_TOOLS) == 6
        for t in ALL_TOOLS:
            assert isinstance(t, BaseTool), f"{t.name} is not a BaseTool"

    def test_tool_names(self):
        from graph.tools import ALL_TOOLS

        names = {t.name for t in ALL_TOOLS}
        expected = {
            "search_usaspending_awards",
            "search_sam_opportunities",
            "search_sec_filings",
            "search_doj_press_releases",
            "search_openfec_committees",
            "search_oversight_reports",
        }
        assert names == expected

    def test_tools_have_descriptions(self):
        from graph.tools import ALL_TOOLS

        for t in ALL_TOOLS:
            assert t.description, f"{t.name} missing description"
            assert len(t.description) > 20, f"{t.name} description too short"

    def test_usaspending_tool_schema(self):
        from graph.tools import search_usaspending_awards

        schema = search_usaspending_awards.args_schema.schema()
        props = schema["properties"]
        assert "recipient_name" in props
        assert "max_pages" in props

    def test_sec_filings_tool_schema(self):
        from graph.tools import search_sec_filings

        schema = search_sec_filings.args_schema.schema()
        props = schema["properties"]
        assert "company_name" in props


# ── Phase 2: System prompt contracts ─────────────────────────────────────────

class TestSystemPrompts:
    def test_evidence_retrieval_prompt_has_sources(self):
        from graph.nodes.evidence_retrieval import SYSTEM_PROMPT

        for source in ["usaspending", "sam_gov", "sec_edgar", "doj", "openfec", "oversight_gov"]:
            assert source in SYSTEM_PROMPT

    def test_graph_builder_prompt_has_relationship_types(self):
        from graph.nodes.graph_builder import SYSTEM_PROMPT

        for rel_type in ["contractor_subcontractor", "officer_of", "subsidiary_of"]:
            assert rel_type in SYSTEM_PROMPT

    def test_anomaly_detector_prompt_forbids_accusations(self):
        from graph.nodes.anomaly_detector import SYSTEM_PROMPT

        assert "never accusations" in SYSTEM_PROMPT.lower() or "never accus" in SYSTEM_PROMPT.lower()
        assert "hypothesis" in SYSTEM_PROMPT.lower()

    def test_anomaly_detector_knows_fraud_patterns(self):
        from graph.nodes.anomaly_detector import SYSTEM_PROMPT

        assert "bid rigging" in SYSTEM_PROMPT.lower()
        assert "shell companies" in SYSTEM_PROMPT.lower()


# ── Phase 3: Per-agent model routing ────────────────────────────────────────

class TestAgentModelRouting:
    def test_agent_model_tier_map_covers_all_agents(self):
        from graph.llm import AGENT_MODEL_TIER

        expected_agents = {
            "entity_resolver", "evidence_retrieval",
            "graph_builder", "anomaly_detector", "case_composer",
        }
        assert set(AGENT_MODEL_TIER.keys()) == expected_agents

    def test_lightweight_agents(self):
        from graph.llm import AGENT_MODEL_TIER

        assert AGENT_MODEL_TIER["entity_resolver"] == "lightweight"
        assert AGENT_MODEL_TIER["evidence_retrieval"] == "lightweight"

    def test_primary_agents(self):
        from graph.llm import AGENT_MODEL_TIER

        assert AGENT_MODEL_TIER["graph_builder"] == "primary"
        assert AGENT_MODEL_TIER["anomaly_detector"] == "primary"
        assert AGENT_MODEL_TIER["case_composer"] == "primary"

    def test_get_agent_llm_lightweight(self):
        try:
            from graph.llm import get_agent_llm
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-14b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("entity_resolver", temperature=0.1)
                assert llm.model_name == "qwen/qwen-2.5-14b-instruct"
        except ImportError:
            pytest.skip("langchain-openai not installed")

    def test_get_agent_llm_primary(self):
        try:
            from graph.llm import get_agent_llm
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-14b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("anomaly_detector", temperature=0.3)
                assert llm.model_name == "qwen/qwen-2.5-72b-instruct"
        except ImportError:
            pytest.skip("langchain-openai not installed")

    def test_get_agent_llm_unknown_defaults_to_primary(self):
        try:
            from graph.llm import get_agent_llm
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-14b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("unknown_agent")
                assert llm.model_name == "qwen/qwen-2.5-72b-instruct"
        except ImportError:
            pytest.skip("langchain-openai not installed")

    def test_lightweight_caps_max_tokens(self):
        try:
            from graph.llm import get_agent_llm
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-14b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("entity_resolver", max_tokens=8192)
                assert llm.max_tokens == 2048
        except ImportError:
            pytest.skip("langchain-openai not installed")


class TestCostTracking:
    def test_callback_instantiation(self):
        from graph.llm import CostTrackingCallback

        cb = CostTrackingCallback(agent_name="test", case_id="case-123")
        assert cb.agent_name == "test"
        assert cb.case_id == "case-123"

    def test_model_costs_defined(self):
        from graph.llm import _MODEL_COSTS

        assert "qwen/qwen-2.5-72b-instruct" in _MODEL_COSTS
        assert "qwen/qwen-2.5-14b-instruct" in _MODEL_COSTS
        for model, costs in _MODEL_COSTS.items():
            assert "input" in costs
            assert "output" in costs
            assert costs["input"] > 0
            assert costs["output"] > 0

    def test_14b_cheaper_than_72b(self):
        from graph.llm import _MODEL_COSTS

        c14 = _MODEL_COSTS["qwen/qwen-2.5-14b-instruct"]
        c72 = _MODEL_COSTS["qwen/qwen-2.5-72b-instruct"]
        assert c14["input"] < c72["input"]
        assert c14["output"] < c72["output"]

    def test_agent_llm_has_callbacks(self):
        try:
            from graph.llm import get_agent_llm, CostTrackingCallback
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-14b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("case_composer", case_id="test-case")
                assert llm.callbacks is not None
                assert any(isinstance(cb, CostTrackingCallback) for cb in llm.callbacks)
        except ImportError:
            pytest.skip("langchain-openai not installed")


class TestMCPServer:
    def test_mcp_app_exists(self):
        from graph.mcp.federal_data import mcp_app
        assert mcp_app is not None
        assert mcp_app.name == "CivicProof Federal Data"

    @pytest.mark.asyncio
    async def test_mcp_tools_registered(self):
        from graph.mcp.federal_data import mcp_app

        tools = await mcp_app.list_tools()
        tool_names = {t.name for t in tools}
        expected = {
            "search_usaspending_awards",
            "search_sam_opportunities",
            "search_sec_filings",
            "search_doj_press_releases",
            "search_openfec_committees",
            "search_oversight_reports",
        }
        assert tool_names == expected

    @pytest.mark.asyncio
    async def test_mcp_tools_have_descriptions(self):
        from graph.mcp.federal_data import mcp_app

        tools = await mcp_app.list_tools()
        for t in tools:
            assert t.description, f"MCP tool {t.name} missing description"
