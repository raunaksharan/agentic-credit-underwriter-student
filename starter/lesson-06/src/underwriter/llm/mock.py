"""A deterministic stand-in for an LLM, with fault injection.

It reads the case JSON the prompt embeds and answers the way a decent but imperfect
model would: it follows the obvious signals, uses a looser DTI cut-off (45%) than
policy (43%), and always produces the requested JSON shape. Same input, same output,
on every machine, with no key.

Faults let lessons 3, 4 and 6 rehearse failures on demand:

    malformed        first reply is not JSON          (repair retry should fix it)
    bad_citation     first reply cites an unknown id   (repair retry should fix it)
    wrong_number     first reply misstates the DTI     (repair retry should fix it)
    *_always         the fault repeats on every call   (escalates to a human)
    unavailable      raises LLMUnavailable             (provider down)

Tool mode (lesson 4): when the system prompt offers tools, the mock behaves like an
agent. It looks up the DTI rule with check_policy, requests a missing document if a
signal says one is missing, then answers. Two extra faults:

    loop             keeps calling check_policy forever (the step cap must stop it)
    disallowed_tool  first tries a tool that is not on the allow-list
"""

from __future__ import annotations

import json
import re

from underwriter.llm.client import LLMResponse, LLMUnavailable, Message

FAULTS = {"malformed", "bad_citation", "wrong_number", "unavailable",
          "malformed_always", "bad_citation_always", "wrong_number_always",
          "loop", "disallowed_tool"}
_DOC_TYPES = ("payslip", "bank_statement", "tax_return", "employment_letter", "id_proof")


def _tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


class MockLLM:
    def __init__(self, fault: str | None = None, model: str = "mock-underwriter-v1") -> None:
        if fault and fault not in FAULTS:
            raise ValueError(f"unknown fault {fault!r}; choose from {sorted(FAULTS)}")
        self.fault = fault
        self.model = model
        self.calls: list[list[Message]] = []
        self.finals = 0  # tool mode: how many final answers we have given

    # -- the "model" -----------------------------------------------------------

    def _answer(self, case: dict) -> dict:
        m = case["metrics"]
        signals = [s for s in case["signals"] if s["severity"] != "info"]
        evidence = [p["id"] for p in case["policy"]][:3]
        figures: dict[str, float] = {}
        risk, missing = [], []
        for s in signals:
            risk.append(s["message"])
            evidence.append(s["id"])
            if s["code"] in ("MISSING_DOCUMENT", "CREDIT_DATA_UNAVAILABLE"):
                missing.append(s["message"])
        if "post_loan_dti" in m:
            figures["post_loan_dti"] = m["post_loan_dti"]["value"]
            evidence.append(m["post_loan_dti"]["id"])
        if "credit_score" in m:
            figures["credit_score"] = m["credit_score"]["value"]
            evidence.append(m["credit_score"]["id"])

        dti = figures.get("post_loan_dti")
        score = figures.get("credit_score")
        if signals:
            rec, why = "MANUAL_REVIEW", "Open risk or data-quality signals need a human decision."
        elif score is not None and score < 600:
            rec, why = "DECLINE", f"Credit score {score:.0f} is weak."
        elif dti is not None and dti > 0.45:
            rec, why = "MANUAL_REVIEW", f"Post-loan DTI of {dti:.1%} is high."
        else:
            parts = []
            if dti is not None:
                parts.append(f"post-loan DTI of {dti:.1%}")
            if score is not None:
                parts.append(f"credit score {score:.0f}")
            rec, why = "APPROVE", "Affordable and creditworthy: " + ", ".join(parts) + "."
        return {"recommendation": rec, "rationale": why, "risk_factors": risk,
                "missing_information": missing, "evidence": evidence, "figures": figures}

    def _faulted(self, answer: dict, first: bool, wrap=None) -> str:
        fault = self.fault
        active = fault and (fault.endswith("_always") or first)
        kind = (fault or "").removesuffix("_always")
        if active and kind == "bad_citation":
            answer["evidence"].append("policy:does-not-exist")
        if active and kind == "wrong_number" and "post_loan_dti" in answer["figures"]:
            wrong = round(answer["figures"]["post_loan_dti"] - 0.1, 4)
            answer["figures"]["post_loan_dti"] = wrong
            answer["rationale"] += f" DTI is {answer['figures']['post_loan_dti']:.1%}."
        text = json.dumps(wrap(answer) if wrap else answer, indent=2)
        if active and kind == "malformed":
            text = "Sure! Here is my assessment:\n" + text[: len(text) // 2]
        return text

    def _agent_step(self, case: dict, messages: list[Message]) -> str:
        results = [json.loads(m) for m in re.findall(
            r"<tool_result name=\"[^\"]*\">\n(.*?)\n</tool_result>",
            "\n".join(x.content for x in messages if x.role == "user"), flags=re.S)]
        used = re.findall(r'"tool": "([a-z_]+)"',
                          "\n".join(x.content for x in messages if x.role == "assistant"))

        def call(tool: str, **arguments) -> str:
            return json.dumps({"action": "call_tool", "tool": tool, "arguments": arguments})

        if self.fault == "loop":
            return call("check_policy", query=f"debt-to-income limit, attempt {len(used) + 1}")
        if self.fault == "disallowed_tool" and not used:
            return call("approve_loan", application_id=case["application"]["application_id"])
        if "check_policy" not in used and "post_loan_dti" in case["metrics"]:
            return call("check_policy", query="debt-to-income ratio limit for personal loans")
        for s in case["signals"]:
            if s["code"] != "MISSING_DOCUMENT":
                continue
            doc = next((d for d in _DOC_TYPES if d in s["message"]), "payslip")
            if "request_missing_document" not in used:
                return call("request_missing_document", doc_type=doc,
                            reason=f"needed to verify income ({s['id']})")

        answer = self._answer(case)
        for r in results:  # cite what the tools returned
            if r.get("results"):
                answer["evidence"].append(r["results"][0]["id"])
            elif r.get("id"):
                answer["evidence"].append(r["id"])
        self.finals += 1
        return self._faulted(answer, self.finals == 1,
                             wrap=lambda a: {"action": "final", "answer": a})

    # -- the port --------------------------------------------------------------

    def complete(self, messages: list[Message], *, max_output_tokens: int = 800,
                 json_mode: bool = False) -> LLMResponse:
        self.calls.append(messages)
        first_call = len(self.calls) == 1
        if self.fault == "unavailable":
            raise LLMUnavailable("mock provider: 503 Service Unavailable")

        prompt = "\n".join(m.content for m in messages)
        user_text = "\n".join(m.content for m in messages if m.role == "user")
        found = re.findall(r"<case_json>\n(.*?)\n</case_json>", user_text, flags=re.S)
        tool_mode = '"action": "call_tool"' in messages[0].content
        if not found:
            text = json.dumps({"reply": "ok"})  # e.g. check-llm's ping
        elif tool_mode:
            text = self._agent_step(json.loads(found[-1]), messages)
        else:
            text = self._faulted(self._answer(json.loads(found[-1])), first_call)
        return LLMResponse(text=text, model=self.model, input_tokens=_tokens(prompt),
                           output_tokens=_tokens(text), latency_ms=5.0)
