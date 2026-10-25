"""Wrap any LLMClient with a span and a meter entry per call (lesson 7).

The wrapper is itself an LLMClient, so nothing else changes. Attribute names follow
the OpenTelemetry GenAI semantic conventions (gen_ai.*), so tracing backends that
understand them can chart tokens and latency per model without custom setup.
Prompts and replies are NOT recorded: they contain case data.
"""

from __future__ import annotations

from underwriter.llm.client import LLMClient, LLMResponse, LLMUnavailable, Message
from underwriter.observability.metering import current_meter
from underwriter.observability.tracing import mark_error, set_attrs, span


class InstrumentedLLM:
    def __init__(self, inner: LLMClient, system: str = "unknown") -> None:
        self.inner = inner
        self.model = inner.model
        self.system = system

    def complete(self, messages: list[Message], *, max_output_tokens: int = 800,
                 json_mode: bool = False) -> LLMResponse:
        with span(f"chat {self.model}", gen_ai__operation__name="chat",
                  gen_ai__system=self.system, gen_ai__request__model=self.model,
                  gen_ai__request__max_tokens=max_output_tokens,
                  llm__messages=len(messages)) as s:
            try:
                resp = self.inner.complete(messages, max_output_tokens=max_output_tokens,
                                           json_mode=json_mode)
            except LLMUnavailable as exc:
                mark_error(s, f"LLMUnavailable: {exc}")
                s.set_attribute("error.type", "LLMUnavailable")
                raise
            meter = current_meter()
            cost = meter.record_llm(resp.model, resp.input_tokens, resp.output_tokens) \
                if meter else None
            set_attrs(s, gen_ai__response__model=resp.model,
                      gen_ai__usage__input_tokens=resp.input_tokens,
                      gen_ai__usage__output_tokens=resp.output_tokens,
                      llm__latency_ms=resp.latency_ms, llm__cost_usd=cost)
            return resp

    # tests and the mock's fault tooling reach through to the wrapped client
    def __getattr__(self, name: str):
        return getattr(self.inner, name)
