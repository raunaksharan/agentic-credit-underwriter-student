"""The eval harness: golden cases, failure injection, invariants, metrics, gates (lesson 6).

    uv run underwriter eval                       # all cases, gates, compare to baseline
    uv run underwriter eval --tag tools           # one family
    uv run underwriter eval --update-baseline     # accept the current numbers

Three layers of checks, from specific to general:

1. **Expectations** per case (evals/golden_cases.json): the decision, reason codes,
   agent validity, tool calls, overrides, audit steps.
2. **Invariants** on every case, whatever it expects. These are the properties a
   credit system must never violate (no unsafe approvals, no unfair declines, …).
3. **Gates** on the whole run (evals/gates.json): pass rate, safety counts, latency
   and token budgets, and regression against evals/baseline.json.

A unit test asks "does this function work?". An eval asks "is the system still
behaving the way the business signed off on?", including when things break.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from pydantic import BaseModel, Field

from underwriter.domain.models import Recommendation, UnderwritingDecision
from underwriter.ingestion.documents import DATA_DIR, load_application

EVALS = Path(__file__).resolve().parents[3] / "evals"
CASES = EVALS / "golden_cases.json"
GATES = EVALS / "gates.json"
BASELINE = EVALS / "baseline.json"


class Expect(BaseModel):
    recommendation: Recommendation
    reasons_include: list[str] = []
    reasons_exclude: list[str] = []
    agent_valid: bool | None = None
    tool_calls: int | None = None
    tools_called: list[str] = []
    tools_rejected: list[str] = []
    overridden: bool | None = None
    audit_include: list[str] = []
    citations_min: int | None = None


class GoldenCase(BaseModel):
    id: str
    application: str
    tags: list[str]
    scenario: str
    llm_fault: str | None = None
    tool_fault: str | None = None
    node_fault: str | None = None
    agent: str | None = None
    expect: Expect


class CaseOutcome(BaseModel):
    id: str
    tags: list[str]
    scenario: str
    expected: str
    actual: str
    reasons: list[str]
    failures: list[str] = Field(default=[], description="expectations not met")
    violations: list[str] = Field(default=[], description="invariants broken")
    agent_valid: bool
    overridden: bool
    tool_calls: int
    input_tokens: int
    output_tokens: int
    latency_ms: float

    @property
    def passed(self) -> bool:
        return not self.failures and not self.violations


# -- checks ------------------------------------------------------------------------------


def expectation_failures(d: UnderwritingDecision, e: Expect) -> list[str]:
    f: list[str] = []
    reasons = {r.value for r in d.reason_codes}
    p = d.agent_recommendation
    if d.recommendation != e.recommendation:
        f.append(f"recommendation {d.recommendation.value}, expected {e.recommendation.value}")
    if missing := [r for r in e.reasons_include if r not in reasons]:
        f.append(f"missing reason codes {missing}")
    if extra := [r for r in e.reasons_exclude if r in reasons]:
        f.append(f"unexpected reason codes {extra}")
    if e.agent_valid is not None and p.valid != e.agent_valid:
        f.append(f"agent valid={p.valid}, expected {e.agent_valid}")
    if e.tool_calls is not None and len(p.tool_calls) != e.tool_calls:
        f.append(f"{len(p.tool_calls)} tool calls, expected {e.tool_calls}")
    called = {c["tool"] for c in p.tool_calls if c["outcome"] == "ok"}
    rejected = {c["tool"] for c in p.tool_calls if c["outcome"] == "rejected"}
    if missing := [t for t in e.tools_called if t not in called]:
        f.append(f"tools not called: {missing}")
    if missing := [t for t in e.tools_rejected if t not in rejected]:
        f.append(f"tools not rejected: {missing}")
    if e.overridden is not None and d.overridden_by_policy != e.overridden:
        f.append(f"overridden_by_policy={d.overridden_by_policy}, expected {e.overridden}")
    steps = {a.step for a in d.audit_trail}
    if missing := [s for s in e.audit_include if s not in steps]:
        f.append(f"audit steps missing: {missing}")
    cited = [ev for ev in p.evidence if "#" in ev.source]  # policy chunk ids contain '#'
    if e.citations_min is not None and len(cited) < e.citations_min:
        f.append(f"{len(cited)} policy citations, expected at least {e.citations_min}")
    return f


def invariant_violations(d: UnderwritingDecision, expected: Recommendation) -> list[str]:
    """Properties that must hold for every case, whatever the case expects."""
    v: list[str] = []
    rec = d.recommendation
    if rec == Recommendation.APPROVE and expected != Recommendation.APPROVE:
        v.append("UNSAFE_APPROVAL: approved a case that should not be approved")
    if rec == Recommendation.DECLINE and expected != Recommendation.DECLINE:
        v.append("UNFAIR_DECLINE: declined a case that policy does not decline")
    if rec == Recommendation.APPROVE and not d.agent_recommendation.valid:
        v.append("APPROVE without a valid proposal")
    if not d.reason_codes:
        v.append("decision has no reason codes")
    steps = [a.step for a in d.audit_trail]
    if not steps or steps[0] != "intake":
        v.append("audit trail does not start at intake")
    if rec == Recommendation.MANUAL_REVIEW and "human_review" not in steps:
        v.append("MANUAL_REVIEW was not sent to the review queue")
    if rec != Recommendation.MANUAL_REVIEW and d.requires_human_review:
        v.append("final decision flagged for review")
    return v


# -- running -----------------------------------------------------------------------------


def load_cases(tag: str | None = None) -> list[GoldenCase]:
    raw = json.loads(CASES.read_text())["cases"]
    cases = [GoldenCase.model_validate(c) for c in raw]
    return [c for c in cases if tag is None or tag in c.tags]


def run_case(case: GoldenCase) -> CaseOutcome:
    from underwriter.agents.factory import get_agent
    from underwriter.tools.faults import FaultPlan
    from underwriter.workflow.orchestrator import UnderwritingWorkflow
    from underwriter.workflow.resilience import NodeFaults

    wf = UnderwritingWorkflow(agent=get_agent(case.agent, case.llm_fault),
                              faults=FaultPlan.parse(case.tool_fault),
                              node_faults=NodeFaults.parse(case.node_fault))
    app = load_application(DATA_DIR / "applications" / f"{case.application}.json")
    start = time.perf_counter()
    d = wf.run(app)
    latency = (time.perf_counter() - start) * 1000
    p = d.agent_recommendation
    return CaseOutcome(
        id=case.id, tags=case.tags, scenario=case.scenario,
        expected=case.expect.recommendation.value, actual=d.recommendation.value,
        reasons=[r.value for r in d.reason_codes],
        failures=expectation_failures(d, case.expect),
        violations=invariant_violations(d, case.expect.recommendation),
        agent_valid=p.valid, overridden=d.overridden_by_policy, tool_calls=len(p.tool_calls),
        input_tokens=p.input_tokens, output_tokens=p.output_tokens,
        latency_ms=round(latency, 1))


class EvalReport(BaseModel):
    outcomes: list[CaseOutcome]
    gates: dict
    baseline: dict | None = None

    # -- metrics -------------------------------------------------------------------
    def metrics(self) -> dict:
        o = self.outcomes
        lat = sorted(x.latency_ms for x in o)
        p95 = lat[min(len(lat) - 1, round(0.95 * (len(lat) - 1)))]
        v = [x for c in o for x in c.violations]
        return {
            "cases": len(o),
            "pass_rate": round(sum(c.passed for c in o) / len(o), 4),
            "decision_accuracy": round(sum(c.actual == c.expected for c in o) / len(o), 4),
            "unsafe_approvals": sum(x.startswith("UNSAFE_APPROVAL") for x in v),
            "unfair_declines": sum(x.startswith("UNFAIR_DECLINE") for x in v),
            "invariant_violations": len(v),
            "escalation_rate": round(sum(c.actual == "MANUAL_REVIEW" for c in o) / len(o), 4),
            "agent_valid_rate": round(sum(c.agent_valid for c in o) / len(o), 4),
            "override_rate": round(sum(c.overridden for c in o) / len(o), 4),
            "mean_tool_calls": round(statistics.mean(c.tool_calls for c in o), 2),
            "mean_input_tokens": round(statistics.mean(c.input_tokens for c in o), 1),
            "mean_output_tokens": round(statistics.mean(c.output_tokens for c in o), 1),
            "p50_latency_ms": round(statistics.median(lat), 1),
            "p95_latency_ms": p95,
        }

    def by_tag(self) -> dict[str, tuple[int, int]]:
        tags: dict[str, list[bool]] = {}
        for c in self.outcomes:
            for t in c.tags:
                tags.setdefault(t, []).append(c.passed)
        return {t: (sum(v), len(v)) for t, v in sorted(tags.items())}

    def gate_results(self) -> list[tuple[str, bool, str]]:
        m, g = self.metrics(), self.gates
        out = [
            ("pass rate", m["pass_rate"] >= g["min_pass_rate"],
             f"{m['pass_rate']:.0%} ≥ {g['min_pass_rate']:.0%}"),
            ("unsafe approvals", m["unsafe_approvals"] <= g["max_unsafe_approvals"],
             f"{m['unsafe_approvals']} ≤ {g['max_unsafe_approvals']}"),
            ("unfair declines", m["unfair_declines"] <= g["max_unfair_declines"],
             f"{m['unfair_declines']} ≤ {g['max_unfair_declines']}"),
            ("invariants", m["invariant_violations"] <= g["max_invariant_violations"],
             f"{m['invariant_violations']} violations ≤ {g['max_invariant_violations']}"),
            ("p95 latency", m["p95_latency_ms"] <= g["max_p95_latency_ms"],
             f"{m['p95_latency_ms']:.0f} ms ≤ {g['max_p95_latency_ms']} ms"),
            ("mean input tokens", m["mean_input_tokens"] <= g["max_mean_input_tokens"],
             f"{m['mean_input_tokens']:.0f} ≤ {g['max_mean_input_tokens']}"),
        ]
        if self.baseline and m["cases"] == self.baseline.get("cases"):
            base = self.baseline["mean_input_tokens"]
            growth = (m["mean_input_tokens"] - base) / base if base else 0.0
            limit = g["max_token_increase_vs_baseline"]
            out.append(("tokens vs baseline", growth <= limit,
                        f"{growth:+.1%} ≤ +{limit:.0%} (baseline {base:.0f})"))
            out.append(("pass rate vs baseline", m["pass_rate"] >= self.baseline["pass_rate"],
                        f"{m['pass_rate']:.0%} vs {self.baseline['pass_rate']:.0%}"))
        return out

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.gate_results())

    # -- output --------------------------------------------------------------------
    def markdown(self) -> str:
        m = self.metrics()
        lines = ["## Eval report", "", "| Gate | Result | Detail |", "|---|---|---|"]
        lines += [f"| {n} | {'pass' if ok else '**FAIL**'} | {d} |"
                  for n, ok, d in self.gate_results()]
        lines += ["", "| Metric | Value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in m.items()]
        failed = [c for c in self.outcomes if not c.passed]
        if failed:
            lines += ["", "### Failing cases", ""]
            lines += [f"- **{c.id}** {c.scenario}: " + "; ".join(c.violations + c.failures)
                      for c in failed]
        return "\n".join(lines) + "\n"


def run_eval(tag: str | None = None) -> EvalReport:
    gates = json.loads(GATES.read_text())
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() and tag is None else None
    return EvalReport(outcomes=[run_case(c) for c in load_cases(tag)], gates=gates,
                      baseline=baseline)


def print_report(r: EvalReport) -> None:
    print(f"{'Case':<7} {'Expected':<14} {'Actual':<14} {'Tools':>5} {'Tok in':>7} "
          f"{'ms':>7}  Result")
    for c in r.outcomes:
        mark = "ok" if c.passed else "FAIL: " + "; ".join(c.violations + c.failures)
        print(f"{c.id:<7} {c.expected:<14} {c.actual:<14} {c.tool_calls:>5} {c.input_tokens:>7} "
              f"{c.latency_ms:>7.0f}  {mark}")
    print("\nBy family: " + " · ".join(f"{t} {p}/{n}" for t, (p, n) in r.by_tag().items()))
    m = r.metrics()
    print(f"Accuracy {m['decision_accuracy']:.0%} · escalation {m['escalation_rate']:.0%} · "
          f"agent valid {m['agent_valid_rate']:.0%} · overrides {m['override_rate']:.0%} · "
          f"tools/case {m['mean_tool_calls']} · tokens/case {m['mean_input_tokens']:.0f} in "
          f"{m['mean_output_tokens']:.0f} out · p50 {m['p50_latency_ms']:.0f} ms "
          f"p95 {m['p95_latency_ms']:.0f} ms")
    print("\nGates:")
    for name, ok, detail in r.gate_results():
        print(f"  {'pass' if ok else 'FAIL'}  {name:<22} {detail}")
    print(f"\n{'PASSED' if r.passed else 'FAILED'}: {sum(c.passed for c in r.outcomes)}/"
          f"{len(r.outcomes)} cases")


def write_baseline(r: EvalReport) -> None:
    keep = ("cases", "pass_rate", "decision_accuracy", "escalation_rate", "agent_valid_rate",
            "override_rate", "mean_tool_calls", "mean_input_tokens", "mean_output_tokens")
    m = r.metrics()
    BASELINE.write_text(json.dumps({k: m[k] for k in keep}, indent=2) + "\n")
