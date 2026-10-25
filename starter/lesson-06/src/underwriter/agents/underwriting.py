"""The LLM underwriting agent (lesson 3).

    case ─► build_context ─► prompt v1 ─► LLM ─► parse ─► validate ──ok──► proposal
                                              ▲                 │
                                              └── repair once ◄─┘ failed again ─► MANUAL_REVIEW

It implements the same UnderwritingAgent contract as lesson 1's rules stub, so the
workflow, the engine and every test around them are unchanged.
"""

from __future__ import annotations

from pathlib import Path

from underwriter.agents.context import build_context
from underwriter.agents.validation import parse_output, semantic_errors
from underwriter.domain.models import (
    AgentRecommendation,
    Evidence,
    ReasonCode,
    Recommendation,
    UnderwritingCase,
)
from underwriter.llm.client import LLMClient, LLMUnavailable, Message

PROMPT_VERSION = "underwriting-v1"
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "underwriting_v1.md").read_text()
MAX_ATTEMPTS = 2  # the first answer plus one repair


def build_messages(case: UnderwritingCase) -> tuple[list[Message], object]:
    ctx = build_context(case)
    user = ("Assess this application. Reply with the JSON object only.\n"
            f"<case_json>\n{ctx.as_json}\n</case_json>")
    return [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user)], ctx


class LLMUnderwritingAgent:
    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.model = client.model

    def recommend(self, case: UnderwritingCase) -> AgentRecommendation:
        messages, ctx = build_messages(case)
        tokens_in = tokens_out = 0
        errors: list[str] = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self.client.complete(messages, max_output_tokens=600, json_mode=True)
            except LLMUnavailable as exc:
                return self._fallback(ReasonCode.MODEL_UNAVAILABLE, [str(exc)], attempt,
                                      tokens_in, tokens_out)
            tokens_in += resp.input_tokens
            tokens_out += resp.output_tokens
            try:
                out = parse_output(resp.text)
                errors = semantic_errors(out, ctx)
            except ValueError as exc:
                out, errors = None, [str(exc)]
            if not errors and out is not None:
                return AgentRecommendation(
                    recommendation=Recommendation(out.recommendation),
                    rationale=out.rationale, risk_factors=out.risk_factors,
                    missing_information=out.missing_information,
                    evidence=[Evidence(source=e, detail=ctx.allowed_ids[e]) for e in out.evidence],
                    model=resp.model, prompt_version=PROMPT_VERSION, attempts=attempt,
                    input_tokens=tokens_in, output_tokens=tokens_out,
                )
            # repair: show the model its own answer and exactly what was wrong with it
            messages = messages + [
                Message(role="assistant", content=resp.text),
                Message(role="user", content="Your answer failed validation:\n- "
                        + "\n- ".join(errors)
                        + "\nReturn the corrected JSON object only."),
            ]
        return self._fallback(ReasonCode.INVALID_MODEL_OUTPUT, errors, MAX_ATTEMPTS,
                              tokens_in, tokens_out)

    def _fallback(self, code: ReasonCode, errors: list[str], attempts: int,
                  tokens_in: int, tokens_out: int) -> AgentRecommendation:
        return AgentRecommendation(
            recommendation=Recommendation.MANUAL_REVIEW,
            rationale=f"No usable model recommendation ({code.value}); a human must decide.",
            missing_information=["A valid model recommendation"],
            model=self.model, prompt_version=PROMPT_VERSION, attempts=attempts,
            valid=False, failure=code, validation_errors=errors,
            input_tokens=tokens_in, output_tokens=tokens_out,
        )
