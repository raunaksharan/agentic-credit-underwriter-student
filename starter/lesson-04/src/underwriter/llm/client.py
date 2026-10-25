"""The LLM port: one small interface every model provider sits behind.

Nothing outside src/underwriter/llm imports a vendor SDK. Swapping OpenAI for Gemini,
Claude or Azure OpenAI is a configuration change (LLM_MODEL), and every test runs on
the deterministic MockLLM with no key and no network.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class LLMUnavailable(Exception):
    """The provider could not answer: timeout, outage, quota, missing key."""


class LLMClient(Protocol):
    model: str

    def complete(self, messages: list[Message], *, max_output_tokens: int = 800,
                 json_mode: bool = False) -> LLMResponse: ...
