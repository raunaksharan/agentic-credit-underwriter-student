"""A bounded tool-calling underwriting agent (lesson 4).

    case ─► context ─► LLM ─┬─ call_tool ─► allow-list ─► tool ─► result ─┐
                            │      ▲                                        │
                            │      └────────────────────────────────────────┘
                            └─ final ─► validate (repair once) ─► proposal

Four limits make the loop safe to run unattended:

1. **Allow-list.** Only the tools in agents/tools.py exist. Anything else is refused
   and the refusal goes back to the model as a tool result, not an exception.
2. **Step cap.** At most MAX_TOOL_CALLS tool calls, then the agent must answer.
3. **Deadline.** A wall-clock budget for the whole loop.
4. **Fallback.** Hitting a limit, or failing validation twice, gives MANUAL_REVIEW with
   a machine-readable reason (AGENT_LIMIT_REACHED, INVALID_MODEL_OUTPUT,
   MODEL_UNAVAILABLE). The engine still decides.

The agent only proposes. Its tools read and request; none of them decides.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from underwriter.agents.context import CaseContext, build_context
from underwriter.agents.tools import build_toolbox
from underwriter.agents.validation import parse_output, semantic_errors
from underwriter.domain.models import (
    AgentRecommendation,
    Evidence,
    ReasonCode,
    Recommendation,
    UnderwritingCase,
)
from underwriter.llm.client import LLMClient, LLMUnavailable, Message
from underwriter.rag.retriever import PolicyRetriever

PROMPT_VERSION = "underwriting-agent-v1"
MAX_TOOL_CALLS = 4
MAX_REPAIRS = 1
DEADLINE_S = float(os.environ.get("AGENT_DEADLINE_S", "30"))
_TEMPLATE = (Path(__file__).parent / "prompts" / "underwriting_agent_v1.md").read_text()


def parse_action(text: str) -> dict:
    """One JSON object with an action. Raises ValueError with a message for the model."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the reply")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply is not valid JSON: {exc.msg}") from exc
    if data.get("action") not in ("call_tool", "final"):
        raise ValueError('"action" must be "call_tool" or "final"')
    return data


class ToolUsingUnderwritingAgent:
    def __init__(self, client: LLMClient, retriever: PolicyRetriever | None = None,
                 max_tool_calls: int = MAX_TOOL_CALLS, deadline_s: float = DEADLINE_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.client = client
        self.model = client.model
        self.retriever = retriever or PolicyRetriever()
        self.max_tool_calls = max_tool_calls
        self.deadline_s = deadline_s
        self.clock = clock

    def build_messages(self, case: UnderwritingCase) -> tuple[list[Message], CaseContext, object]:
        ctx = build_context(case)
        box = build_toolbox(case, self.retriever)
        system = (_TEMPLATE.replace("{max_steps}", str(self.max_tool_calls))
                  .replace("{tools}", box.describe()))
        user = ("Assess this application. Use tools if they help, then give your final "
                f"answer.\n<case_json>\n{ctx.as_json}\n</case_json>")
        return [Message(role="system", content=system), Message(role="user", content=user)], \
            ctx, box

    def recommend(self, case: UnderwritingCase) -> AgentRecommendation:
        messages, ctx, box = self.build_messages(case)
        started = self.clock()
        calls: list[dict] = []
        repairs = 0
        tokens = [0, 0]
        llm_calls = 0

        def fail(code: ReasonCode, errors: list[str]) -> AgentRecommendation:
            return self._fallback(code, errors, llm_calls, tokens, calls)

        while True:
            if self.clock() - started > self.deadline_s:
                return fail(ReasonCode.AGENT_LIMIT_REACHED,
                            [f"deadline of {self.deadline_s:.0f}s exceeded"])
            try:
                resp = self.client.complete(messages, max_output_tokens=700, json_mode=True)
            except LLMUnavailable as exc:
                return fail(ReasonCode.MODEL_UNAVAILABLE, [str(exc)])
            llm_calls += 1
            tokens[0] += resp.input_tokens
            tokens[1] += resp.output_tokens
            messages = messages + [Message(role="assistant", content=resp.text)]

            try:
                action = parse_action(resp.text)
            except ValueError as exc:
                if repairs >= MAX_REPAIRS:
                    return fail(ReasonCode.INVALID_MODEL_OUTPUT, [str(exc)])
                repairs += 1
                messages.append(Message(role="user", content=f"Invalid reply: {exc}. "
                                        "Reply with one JSON object only."))
                continue

            if action["action"] == "call_tool":
                if len(calls) >= self.max_tool_calls:
                    return fail(ReasonCode.AGENT_LIMIT_REACHED,
                                [f"tool budget of {self.max_tool_calls} calls exhausted"])
                name = str(action.get("tool", ""))
                args = action.get("arguments") or {}
                ok, result = box.call(name, args if isinstance(args, dict) else {})
                calls.append({"tool": name, "arguments": args,
                              "outcome": "ok" if ok else "rejected",
                              "detail": result.get("error", "")})
                messages.append(Message(role="user", content=f'<tool_result name="{name}">\n'
                                        f"{json.dumps(result)}\n</tool_result>"))
                continue

            # final answer: validate against the context plus everything tools returned
            full_ctx = ctx.model_copy(update={"allowed_ids": {**ctx.allowed_ids, **box.new_ids}})
            try:
                out = parse_output(json.dumps(action.get("answer", {})))
                errors = semantic_errors(out, full_ctx)
            except ValueError as exc:
                out, errors = None, [str(exc)]
            if out is not None and not errors:
                missing = list(out.missing_information)
                missing += [f"{d['doc_type']} (requested)" for d in box.requested_documents
                            if not any(d["doc_type"] in m for m in missing)]
                return AgentRecommendation(
                    recommendation=Recommendation(out.recommendation),
                    rationale=out.rationale, risk_factors=out.risk_factors,
                    missing_information=missing,
                    evidence=[Evidence(source=e, detail=full_ctx.allowed_ids[e])
                              for e in out.evidence],
                    model=resp.model, prompt_version=PROMPT_VERSION, attempts=llm_calls,
                    input_tokens=tokens[0], output_tokens=tokens[1], tool_calls=calls)
            if repairs >= MAX_REPAIRS:
                return fail(ReasonCode.INVALID_MODEL_OUTPUT, errors)
            repairs += 1
            messages.append(Message(role="user", content="Your final answer failed validation:"
                                    "\n- " + "\n- ".join(errors)
                                    + "\nReturn the corrected final JSON object only."))

    def _fallback(self, code: ReasonCode, errors: list[str], attempts: int,
                  tokens: list[int], calls: list[dict]) -> AgentRecommendation:
        return AgentRecommendation(
            recommendation=Recommendation.MANUAL_REVIEW,
            rationale=f"No usable agent recommendation ({code.value}); a human must decide.",
            missing_information=["A valid agent recommendation"],
            model=self.model, prompt_version=PROMPT_VERSION, attempts=attempts, valid=False,
            failure=code, validation_errors=errors, input_tokens=tokens[0],
            output_tokens=tokens[1], tool_calls=calls)
