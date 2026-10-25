"""Real providers through LiteLLM (optional install: `uv sync --extra llm`).

LiteLLM speaks one API to many providers; the model string picks the provider, e.g.
"gpt-4o-mini", "gemini/gemini-2.0-flash", "anthropic/claude-…", "azure/<deployment>".
Use whatever model your provider currently offers; nothing here hardcodes one.
Keys come from the provider's usual environment variable (OPENAI_API_KEY,
GEMINI_API_KEY, ANTHROPIC_API_KEY, AZURE_API_KEY, …).
"""

from __future__ import annotations

import time

from underwriter.llm.client import LLMResponse, LLMUnavailable, Message


class LiteLLMClient:
    def __init__(self, model: str, timeout_s: float = 30.0, temperature: float = 0.0) -> None:
        try:
            import litellm  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise LLMUnavailable(
                "LLM_MODE=live needs the optional 'llm' extra: uv sync --extra llm"
            ) from exc
        self.model = model
        self.timeout_s = timeout_s
        self.temperature = temperature

    def complete(self, messages: list[Message], *, max_output_tokens: int = 800,
                 json_mode: bool = False) -> LLMResponse:  # pragma: no cover - needs a key
        import litellm

        kwargs: dict = dict(model=self.model, messages=[m.model_dump() for m in messages],
                            max_tokens=max_output_tokens, temperature=self.temperature,
                            timeout=self.timeout_s)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.perf_counter()
        try:
            resp = litellm.completion(**kwargs)
        except Exception as exc:  # provider errors vary; the caller only needs one type
            raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=resp.choices[0].message.content or "",
            model=getattr(resp, "model", None) or self.model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
