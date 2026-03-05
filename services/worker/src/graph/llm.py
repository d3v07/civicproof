"""LLM factory with cascading fallback: OpenRouter → Gemini → Ollama.

Each provider is tried in order. If a provider's API key is missing or
the call fails (402 payment required, timeout, etc.), we fall through
to the next. Cost tracking via callback on every successful call.
"""

from __future__ import annotations

import logging
from typing import Any

from civicproof_common.config import get_settings
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

# Maps agent name → "primary" or "lightweight"
AGENT_MODEL_TIER: dict[str, str] = {
    "entity_resolver": "lightweight",
    "evidence_retrieval": "lightweight",
    "graph_builder": "primary",
    "anomaly_detector": "primary",
    "case_composer": "primary",
}

_MODEL_COSTS: dict[str, dict[str, float]] = {
    "qwen/qwen-2.5-72b-instruct": {"input": 0.33e-6, "output": 0.39e-6},
    "qwen/qwen-2.5-7b-instruct": {"input": 0.04e-6, "output": 0.07e-6},
    "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
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


def _build_openrouter(
    model: str,
    temperature: float,
    max_tokens: int,
    callbacks: list | None,
) -> BaseChatModel | None:
    """Try to build OpenRouter LLM. Returns None if no API key."""
    settings = get_settings()
    if not settings.OPENROUTER_API_KEY:
        return None
    from langchain_openai import ChatOpenAI
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


def _build_gemini(
    temperature: float,
    max_tokens: int,
    callbacks: list | None,
) -> BaseChatModel | None:
    """Try to build Gemini LLM. Returns None if no API key."""
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.VERTEX_AI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
            max_output_tokens=max_tokens,
            callbacks=callbacks,
        )
    except Exception as exc:
        logger.warning("gemini_init_failed: %s", exc)
        return None


def _build_ollama(
    temperature: float,
    callbacks: list | None,
) -> BaseChatModel | None:
    """Try to build Ollama LLM. Returns None if Ollama not reachable."""
    settings = get_settings()
    try:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
            callbacks=callbacks,
        )
    except Exception as exc:
        logger.warning("ollama_init_failed: %s", exc)
        return None


class CascadingLLM(BaseChatModel):
    """Wraps multiple LLMs and falls through on failure.

    Tries each provider in order. On any exception (402, timeout,
    connection error), logs and tries the next.
    """

    providers: list[Any]
    provider_names: list[str]

    @property
    def _llm_type(self) -> str:
        return "cascading"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last_exc = None
        for i, provider in enumerate(self.providers):
            try:
                return provider._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                name = self.provider_names[i] if i < len(self.provider_names) else f"provider_{i}"
                logger.warning("llm_fallback provider=%s error=%s", name, exc)
                last_exc = exc
        raise last_exc or RuntimeError("No LLM providers available")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        last_exc = None
        for i, provider in enumerate(self.providers):
            try:
                return await provider._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
            except Exception as exc:
                name = self.provider_names[i] if i < len(self.provider_names) else f"provider_{i}"
                logger.warning("llm_fallback provider=%s error=%s", name, exc)
                last_exc = exc
        raise last_exc or RuntimeError("No LLM providers available")


def get_llm(
    temperature: float = 0.2,
    max_tokens: int = 1024,
    model_override: str | None = None,
    callbacks: list | None = None,
) -> BaseChatModel:
    """Build a cascading LLM: OpenRouter → Gemini → Ollama."""
    settings = get_settings()
    model = model_override or settings.LLM_MODEL_PRIMARY

    providers: list[BaseChatModel] = []
    names: list[str] = []

    openrouter = _build_openrouter(model, temperature, max_tokens, callbacks)
    if openrouter:
        providers.append(openrouter)
        names.append(f"openrouter:{model}")

    gemini = _build_gemini(temperature, max_tokens, callbacks)
    if gemini:
        providers.append(gemini)
        names.append(f"gemini:{settings.VERTEX_AI_MODEL}")

    ollama = _build_ollama(temperature, callbacks)
    if ollama:
        providers.append(ollama)
        names.append(f"ollama:{settings.OLLAMA_MODEL}")

    if not providers:
        logger.error("no_llm_providers_available — check OPENROUTER_API_KEY, GEMINI_API_KEY, or Ollama")
        raise RuntimeError(
            "No LLM providers configured. Set OPENROUTER_API_KEY, GEMINI_API_KEY, "
            "or run Ollama locally."
        )

    if len(providers) == 1:
        logger.info("llm_provider single=%s", names[0])
        return providers[0]

    logger.info("llm_cascade chain=%s", " → ".join(names))
    return CascadingLLM(providers=providers, provider_names=names)


def get_lightweight_llm(
    temperature: float = 0.1,
    max_tokens: int = 512,
    callbacks: list | None = None,
) -> BaseChatModel:
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
    max_tokens: int = 1024,
    case_id: str = "",
) -> BaseChatModel:
    """Return the right LLM for a given agent, with cost tracking."""
    tier = AGENT_MODEL_TIER.get(agent_name, "primary")
    cb = CostTrackingCallback(agent_name=agent_name, case_id=case_id)
    if tier == "lightweight":
        return get_lightweight_llm(
            temperature=temperature,
            max_tokens=min(max_tokens, 512),
            callbacks=[cb],
        )
    return get_llm(
        temperature=temperature,
        max_tokens=max_tokens,
        callbacks=[cb],
    )
