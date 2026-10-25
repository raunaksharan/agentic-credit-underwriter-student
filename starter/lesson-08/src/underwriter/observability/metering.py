"""Per-decision usage metering (lesson 7): tokens, model calls, cost, time per step.

Every LLM call reports into the meter of the decision being made. The meter lives
in a context variable, so concurrent decisions never mix their numbers, and it is
copied into worker threads with the rest of the context (see workflow/resilience.py).

Prices are a table in code, per million tokens, in USD. They are placeholders for
the class: check your provider's current price list and put the real numbers in
PRICES, or set LLM_PRICE_IN / LLM_PRICE_OUT for the model you use.
"""

from __future__ import annotations

import contextvars
import os
from collections import defaultdict
from contextlib import contextmanager

from pydantic import BaseModel, Field

# USD per 1M tokens: (input, output). Placeholders: verify against your provider.
PRICES: dict[str, tuple[float, float]] = {
    "mock-underwriter-v1": (0.0, 0.0),
}


class ModelUsage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Usage(BaseModel):
    """What one decision cost. Travels with the decision."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cost_known: bool = Field(True, description="False if a model had no price")
    by_model: dict[str, ModelUsage] = {}
    step_ms: dict[str, float] = Field({}, description="wall-clock time per workflow step")
    total_ms: float = 0.0


def price_for(model: str) -> tuple[float, float] | None:
    if model in PRICES:
        return PRICES[model]
    if os.environ.get("LLM_PRICE_IN") and os.environ.get("LLM_PRICE_OUT"):
        return float(os.environ["LLM_PRICE_IN"]), float(os.environ["LLM_PRICE_OUT"])
    return None


class UsageMeter:
    def __init__(self) -> None:
        self.usage = Usage()
        self._steps: dict[str, float] = defaultdict(float)

    def record_llm(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        u = self.usage
        m = u.by_model.setdefault(model, ModelUsage())
        price = price_for(model)
        cost = None
        if price is None:
            u.cost_known = False
        else:
            cost = (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000
            m.cost_usd += cost
            u.cost_usd += cost
        m.calls += 1
        m.input_tokens += input_tokens
        m.output_tokens += output_tokens
        u.llm_calls += 1
        u.input_tokens += input_tokens
        u.output_tokens += output_tokens
        return cost

    def record_step(self, step: str, ms: float) -> None:
        self._steps[step] += ms
        self.usage.step_ms = {k: round(v, 1) for k, v in self._steps.items()}


_current: contextvars.ContextVar[UsageMeter | None] = contextvars.ContextVar(
    "usage_meter", default=None)


def current_meter() -> UsageMeter | None:
    return _current.get()


@contextmanager
def metering():
    meter = UsageMeter()
    token = _current.set(meter)
    try:
        yield meter
    finally:
        _current.reset(token)
