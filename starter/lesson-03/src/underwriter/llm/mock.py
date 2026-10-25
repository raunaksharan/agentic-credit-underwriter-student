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
"""

from __future__ import annotations

import json
import re

from underwriter.llm.client import LLMResponse, LLMUnavailable, Message

FAULTS = {"malformed", "bad_citation", "wrong_number", "unavailable",
          "malformed_always", "bad_citation_always", "wrong_number_always"}


def _tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


class MockLLM:
    def __init__(self, fault: str | None = None, model: str = "mock-underwriter-v1") -> None:
        if fault and fault not in FAULTS:
            raise ValueError(f"unknown fault {fault!r}; choose from {sorted(FAULTS)}")
        self.fault = fault
        self.model = model
        self.calls: list[list[Message]] = []

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

    # -- the port --------------------------------------------------------------

    def complete(self, messages: list[Message], *, max_output_tokens: int = 800,
                 json_mode: bool = False) -> LLMResponse:
        self.calls.append(messages)
        first_call = len(self.calls) == 1
        fault = self.fault
        if fault == "unavailable":
            raise LLMUnavailable("mock provider: 503 Service Unavailable")

        prompt = "\n".join(m.content for m in messages)
        user_text = "\n".join(m.content for m in messages if m.role == "user")
        found = re.findall(r"<case_json>\n(.*?)\n</case_json>", user_text, flags=re.S)
        if not found:
            text = json.dumps({"reply": "ok"})  # e.g. check-llm's ping
        else:
            answer = self._answer(json.loads(found[-1]))
            active = fault and (fault.endswith("_always") or first_call)
            kind = (fault or "").removesuffix("_always")
            if active and kind == "bad_citation":
                answer["evidence"].append("policy:does-not-exist")
            if active and kind == "wrong_number" and "post_loan_dti" in answer["figures"]:
                wrong = round(answer["figures"]["post_loan_dti"] - 0.1, 4)
                answer["figures"]["post_loan_dti"] = wrong
                answer["rationale"] += f" DTI is {answer['figures']['post_loan_dti']:.1%}."
            text = json.dumps(answer, indent=2)
            if active and kind == "malformed":
                text = "Sure! Here is my assessment:\n" + text[: len(text) // 2]
        return LLMResponse(text=text, model=self.model, input_tokens=_tokens(prompt),
                           output_tokens=_tokens(text), latency_ms=5.0)
