"""Pick the LLM client from the environment.

    LLM_MODE=mock (default)   deterministic MockLLM, no key, no network
    LLM_MODE=live             LiteLLMClient(LLM_MODEL); needs `uv sync --extra llm`
    LLM_MODEL=...             any LiteLLM model string your provider offers
    LLM_TIMEOUT_S=30          per-call timeout for live mode
    LLM_FAULT=malformed       mock only: rehearse a failure (see llm/mock.py)
"""

from __future__ import annotations

import os

from underwriter.llm.client import LLMClient, LLMUnavailable
from underwriter.llm.mock import MockLLM


def get_llm_client(fault: str | None = None) -> LLMClient:
    mode = os.environ.get("LLM_MODE", "mock").lower()
    from underwriter.llm.instrumented import InstrumentedLLM  # lesson 7: spans + metering
    if mode == "mock":
        return InstrumentedLLM(MockLLM(fault=fault or os.environ.get("LLM_FAULT") or None),
                               system="mock")
    if mode == "live":
        model = os.environ.get("LLM_MODEL")
        if not model:
            raise LLMUnavailable("LLM_MODE=live needs LLM_MODEL, e.g. LLM_MODEL=gpt-4o-mini")
        from underwriter.llm.litellm_client import LiteLLMClient

        return InstrumentedLLM(
            LiteLLMClient(model, timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "30"))),
            system=model.split("/", 1)[0] if "/" in model else "litellm")
    raise ValueError(f"LLM_MODE must be 'mock' or 'live', not {mode!r}")
