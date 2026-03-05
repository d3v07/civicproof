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
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-7b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.GEMINI_API_KEY = None
                mock_settings.return_value.OLLAMA_BASE_URL = "http://localhost:11434"
                mock_settings.return_value.OLLAMA_MODEL = "qwen2.5:7b"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("entity_resolver", max_tokens=8192)
                from graph.llm import CascadingLLM
                target = llm.providers[0] if isinstance(llm, CascadingLLM) else llm
                assert target.max_tokens == 512
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
        assert "qwen/qwen-2.5-7b-instruct" in _MODEL_COSTS
        for model, costs in _MODEL_COSTS.items():
            assert "input" in costs
            assert "output" in costs
            assert costs["input"] >= 0
            assert costs["output"] >= 0

    def test_7b_cheaper_than_72b(self):
        from graph.llm import _MODEL_COSTS

        c7 = _MODEL_COSTS["qwen/qwen-2.5-7b-instruct"]
        c72 = _MODEL_COSTS["qwen/qwen-2.5-72b-instruct"]
        assert c7["input"] < c72["input"]
        assert c7["output"] < c72["output"]

    def test_agent_llm_has_callbacks(self):
        try:
            from graph.llm import get_agent_llm, CostTrackingCallback
            from unittest.mock import patch

            with patch("graph.llm.get_settings") as mock_settings:
                mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
                mock_settings.return_value.LLM_MODEL_LIGHTWEIGHT = "qwen/qwen-2.5-7b-instruct"
                mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
                mock_settings.return_value.GEMINI_API_KEY = None
                mock_settings.return_value.OLLAMA_BASE_URL = "http://localhost:11434"
                mock_settings.return_value.OLLAMA_MODEL = "qwen2.5:7b"
                mock_settings.return_value.LLM_MAX_RETRIES = 2

                llm = get_agent_llm("case_composer", case_id="test-case")
                # Single provider: callbacks on the LLM directly
                # CascadingLLM: callbacks on inner providers
                from graph.llm import CascadingLLM
                if isinstance(llm, CascadingLLM):
                    inner = llm.providers[0]
                    assert inner.callbacks is not None
                    assert any(isinstance(cb, CostTrackingCallback) for cb in inner.callbacks)
                else:
                    assert llm.callbacks is not None
                    assert any(isinstance(cb, CostTrackingCallback) for cb in llm.callbacks)
        except ImportError:
            pytest.skip("langchain-openai not installed")


class TestCascadingLLM:
    def test_cascading_llm_type(self):
        from graph.llm import CascadingLLM
        assert CascadingLLM is not None

    def test_cascading_falls_through_on_error(self):
        from graph.llm import CascadingLLM
        from langchain_core.messages import AIMessage
        from unittest.mock import MagicMock

        provider_a = MagicMock()
        provider_a._generate.side_effect = Exception("402 Payment Required")
        provider_b = MagicMock()
        mock_result = MagicMock()
        mock_result.generations = [[MagicMock(text="ok")]]
        provider_b._generate.return_value = mock_result

        cascade = CascadingLLM(
            providers=[provider_a, provider_b],
            provider_names=["openrouter", "gemini"],
        )
        result = cascade._generate([])
        provider_a._generate.assert_called_once()
        provider_b._generate.assert_called_once()
        assert result == mock_result

    def test_cascading_uses_first_if_success(self):
        from graph.llm import CascadingLLM
        from unittest.mock import MagicMock

        provider_a = MagicMock()
        mock_result = MagicMock()
        provider_a._generate.return_value = mock_result
        provider_b = MagicMock()

        cascade = CascadingLLM(
            providers=[provider_a, provider_b],
            provider_names=["openrouter", "gemini"],
        )
        result = cascade._generate([])
        provider_a._generate.assert_called_once()
        provider_b._generate.assert_not_called()

    def test_cascading_raises_if_all_fail(self):
        from graph.llm import CascadingLLM
        from unittest.mock import MagicMock

        provider_a = MagicMock()
        provider_a._generate.side_effect = Exception("fail a")
        provider_b = MagicMock()
        provider_b._generate.side_effect = Exception("fail b")

        cascade = CascadingLLM(
            providers=[provider_a, provider_b],
            provider_names=["a", "b"],
        )
        with pytest.raises(Exception, match="fail b"):
            cascade._generate([])

    @pytest.mark.asyncio
    async def test_cascading_async_fallback(self):
        from graph.llm import CascadingLLM
        from unittest.mock import AsyncMock, MagicMock

        provider_a = MagicMock()
        provider_a._agenerate = AsyncMock(side_effect=Exception("timeout"))
        provider_b = MagicMock()
        mock_result = MagicMock()
        provider_b._agenerate = AsyncMock(return_value=mock_result)

        cascade = CascadingLLM(
            providers=[provider_a, provider_b],
            provider_names=["openrouter", "gemini"],
        )
        result = await cascade._agenerate([])
        assert result == mock_result

    def test_get_llm_no_providers_raises(self):
        from unittest.mock import patch
        from graph.llm import get_llm

        with patch("graph.llm.get_settings") as mock_settings:
            mock_settings.return_value.OPENROUTER_API_KEY = None
            mock_settings.return_value.GEMINI_API_KEY = None
            mock_settings.return_value.OLLAMA_BASE_URL = "http://localhost:11434"
            mock_settings.return_value.OLLAMA_MODEL = "qwen2.5:7b"
            mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
            mock_settings.return_value.LLM_MAX_RETRIES = 2
            # Patch _build_ollama to return None (simulates unreachable)
            with patch("graph.llm._build_ollama", return_value=None):
                with pytest.raises(RuntimeError, match="No LLM providers configured"):
                    get_llm()

    def test_get_llm_single_provider_no_cascade(self):
        from unittest.mock import patch, MagicMock
        from graph.llm import get_llm, CascadingLLM

        with patch("graph.llm.get_settings") as mock_settings:
            mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
            mock_settings.return_value.GEMINI_API_KEY = None
            mock_settings.return_value.OLLAMA_BASE_URL = "http://localhost:11434"
            mock_settings.return_value.OLLAMA_MODEL = "qwen2.5:7b"
            mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
            mock_settings.return_value.LLM_MAX_RETRIES = 2
            with patch("graph.llm._build_ollama", return_value=None):
                llm = get_llm()
                assert not isinstance(llm, CascadingLLM)

    def test_get_llm_multiple_providers_cascades(self):
        from unittest.mock import patch, MagicMock
        from graph.llm import get_llm, CascadingLLM

        mock_gemini = MagicMock()
        with patch("graph.llm.get_settings") as mock_settings:
            mock_settings.return_value.OPENROUTER_API_KEY = "test-key"
            mock_settings.return_value.GEMINI_API_KEY = "test-gemini"
            mock_settings.return_value.VERTEX_AI_MODEL = "gemini-2.0-flash"
            mock_settings.return_value.OLLAMA_BASE_URL = "http://localhost:11434"
            mock_settings.return_value.OLLAMA_MODEL = "qwen2.5:7b"
            mock_settings.return_value.LLM_MODEL_PRIMARY = "qwen/qwen-2.5-72b-instruct"
            mock_settings.return_value.LLM_MAX_RETRIES = 2
            with patch("graph.llm._build_gemini", return_value=mock_gemini), \
                 patch("graph.llm._build_ollama", return_value=None):
                llm = get_llm()
                assert isinstance(llm, CascadingLLM)
                assert len(llm.providers) == 2


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
