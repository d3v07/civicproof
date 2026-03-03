"""LLM factory for OpenRouter via LangChain's ChatOpenAI.

Per-agent model routing: lightweight (14B) for simple structuring tasks,
full (72B) for reasoning-heavy analysis. Cost tracking via callback.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from civicproof_common.config import get_settings
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# Maps agent name → "primary" or "lightweight"
AGENT_MODEL_TIER: dict[str, str] = {
    "entity_resolver": "lightweight",    # Simple disambiguation, structured output
    "evidence_retrieval": "lightweight",  # Query planning, low reasoning
    "graph_builder": "primary",           # Relationship extraction from documents
    "anomaly_detector": "primary",        # Cross-signal hypothesis generation
    "case_composer": "primary",           # Narrative generation, complex output
}

# Approximate per-token costs (USD) for OpenRouter models
_MODEL_COSTS: dict[str, dict[str, float]] = {
    "qwen/qwen-2.5-72b-instruct": {"input": 0.33e-6, "output": 0.39e-6},
    "qwen/qwen-2.5-14b-instruct": {"input": 0.07e-6, "output": 0.14e-6},
}


class CostTrackingCallback(BaseCallbackHandler):
    """Tracks token usage and estimated cost per LLM call."""

    def __init__(self, agent_name: str = "unknown", case_id: str = ""):
        self.agent_name = agent_name
        self.case_id = case_id

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = {}
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
        if not usage and response.generations:
            gen = response.generations[0][0] if response.generations[0] else None
            if gen and hasattr(gen, "generation_info") and gen.generation_info:
                usage = gen.generation_info.get("token_usage", {})

        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        model = (response.llm_output or {}).get("model_name", "unknown")
        costs = _MODEL_COSTS.get(model, {"input": 0.33e-6, "output": 0.39e-6})
        estimated_cost = (input_tokens * costs["input"]) + (output_tokens * costs["output"])

        logger.info(
            "llm_usage agent=%s case_id=%s model=%s "
            "input_tokens=%d output_tokens=%d estimated_cost_usd=%.6f",
            self.agent_name, self.case_id, model,
            input_tokens, output_tokens, estimated_cost,
        )


def get_llm(
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model_override: str | None = None,
    callbacks: list | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    model = model_override or settings.LLM_MODEL_PRIMARY
    return ChatOpenAI(
        model=model,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=settings.LLM_MAX_RETRIES,
        default_headers={
            "HTTP-Referer": "https://civicproof.ai",
            "X-Title": "CivicProof",
        },
        callbacks=callbacks,
    )


def get_lightweight_llm(
    temperature: float = 0.1,
    max_tokens: int = 2048,
    callbacks: list | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    return get_llm(
        temperature=temperature,
        max_tokens=max_tokens,
        model_override=settings.LLM_MODEL_LIGHTWEIGHT,
        callbacks=callbacks,
    )


def get_agent_llm(
    agent_name: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    case_id: str = "",
) -> ChatOpenAI:
    """Return the right LLM for a given agent, with cost tracking."""
    tier = AGENT_MODEL_TIER.get(agent_name, "primary")
    cb = CostTrackingCallback(agent_name=agent_name, case_id=case_id)
    if tier == "lightweight":
        return get_lightweight_llm(
            temperature=temperature,
            max_tokens=min(max_tokens, 2048),
            callbacks=[cb],
        )
    return get_llm(
        temperature=temperature,
        max_tokens=max_tokens,
        callbacks=[cb],
    )
