"""The underwriting workflow as a LangGraph graph (lesson 5).

    START → intake → income → checks → analyze → policy → agent → engine ─┬─→ END
               │        │        │         │                               │
               └────────┴────────┴─────────┴──→ escalate ──→ human_review ←┘ (MANUAL_REVIEW)
                                                                   │
                                                          interrupt() │ resume(HumanReview)
                                                                   ▼
                                                                  END

- **Typed state.** `UnderwritingState` is the only thing nodes share. Each node reads
  what it needs and returns the keys it changed; `audit` is appended, never replaced.
- **Per-node policy.** Every node runs through `run_node` with its own timeout, retry
  count and failure mode (`NODE_POLICIES`). Required steps escalate; policy retrieval
  degrades; the agent has its own fallback.
- **Human-review edge.** MANUAL_REVIEW goes to `human_review`, which queues the case
  and, when the run is interactive, pauses the graph with `interrupt()` until a
  reviewer resumes it with a `HumanReview`. The pause is checkpointed by thread id.

The nodes call the same components as lessons 1–4; only the control flow moved here.
"""

from __future__ import annotations

import operator
import time
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from opentelemetry import trace

from underwriter.decision.policy import POLICY_VERSION
from underwriter.domain.models import (
    AgentRecommendation,
    AnalysisResult,
    AuditEvent,
    CheckResult,
    HumanReview,
    LoanApplication,
    ReasonCode,
    Recommendation,
    RiskSignal,
    UnderwritingCase,
    UnderwritingDecision,
)
from underwriter.observability.metering import current_meter
from underwriter.observability.tracing import mark_error, redact, set_attrs, span
from underwriter.workflow.resilience import NodeFailed, NodeFaults, NodePolicy, run_node

NODE_POLICIES: dict[str, NodePolicy] = {
    "income": NodePolicy(timeout_s=2.0, max_attempts=2),
    "checks": NodePolicy(timeout_s=10.0),            # each check has its own status
    "analyze": NodePolicy(timeout_s=2.0),
    "policy": NodePolicy(timeout_s=3.0, max_attempts=2, on_failure="degrade"),
    "agent": NodePolicy(timeout_s=60.0, on_failure="fallback"),  # has its own deadline
    "engine": NodePolicy(timeout_s=1.0),
}


class UnderwritingState(TypedDict, total=False):
    application: LoanApplication
    interactive: bool
    income: Any
    income_result: AnalysisResult
    checks: list[CheckResult]
    case: UnderwritingCase
    proposal: AgentRecommendation
    decision: UnderwritingDecision
    failure: dict | None                     # {"node", "attempts", "reason"} → escalate
    audit: Annotated[list[AuditEvent], operator.add]


def _event(step: str, actor: str, summary: str, **data) -> AuditEvent:
    return AuditEvent(step=step, actor=actor, summary=summary, data=data)


def build_graph(wf, faults: NodeFaults | None = None, policies: dict | None = None,
                checkpointer=None):
    """Compile the graph over an UnderwritingWorkflow's components."""
    faults = faults or NodeFaults()
    policies = {**NODE_POLICIES, **(policies or {})}

    def guarded(name: str, fn, state: UnderwritingState, on_ok):
        """Run one node under its policy; turn failure into state, not an exception.

        Lesson 7: each node is a span (attempts, outcome) and its time goes to the meter.
        """
        policy = policies[name]
        start = time.perf_counter()
        with span(f"node {name}", node__name=name, node__timeout_s=policy.timeout_s,
                  node__max_attempts=policy.max_attempts) as s:
            try:
                try:
                    run = run_node(name, fn, policy, faults)
                except NodeFailed as exc:
                    set_attrs(s, node__attempts=exc.attempts, node__outcome=policy.on_failure,
                              node__error=redact(exc.reason))
                    mark_error(s, str(exc))
                    event = _event("node_failure", f"node:{name}", str(exc),
                                   attempts=exc.attempts, on_failure=policy.on_failure)
                    if policy.on_failure == "escalate":
                        return {"failure": {"node": name, "attempts": exc.attempts,
                                            "reason": exc.reason}, "audit": [event]}
                    update = on_ok(None, state)  # degrade / fallback: a default from the node
                    update["audit"] = [event] + update.get("audit", [])
                    return update
                set_attrs(s, node__attempts=run.attempts,
                          node__outcome="retried" if run.attempts > 1 else "ok")
                update = on_ok(run.value, state)
                if run.attempts > 1:
                    update["audit"] = [_event("node_retry", f"node:{name}",
                                              f"succeeded on attempt {run.attempts}",
                                              errors=run.errors)] + update.get("audit", [])
                return update
            finally:
                meter = current_meter()
                if meter:
                    meter.record_step(name, (time.perf_counter() - start) * 1000)

    # -- nodes ---------------------------------------------------------------------

    def intake(state: UnderwritingState):
        app = state["application"]
        return {"failure": None, "audit": [_event(
            "intake", "workflow", f"Received {app.application_id}",
            documents=[d.doc_type.value for d in app.documents])]}

    def income(state: UnderwritingState):
        app = state["application"]

        def ok(value, _):
            inc, result = value
            return {"income": inc, "income_result": result, "audit": [_event(
                "income_verification", "income_verification",
                f"Verified monthly income: {inc.monthly_gross_income}", method=inc.method)]}
        return guarded("income", lambda: wf.income_verifier.verify(app), state, ok)

    def checks(state: UnderwritingState):
        app = state["application"]

        def ok(results, _):
            return {"checks": results, "audit": [
                _event("check", f"tool:{c.tool}",
                       c.status.value + (f": {c.reason}" if c.reason else ""),
                       required=c.required, latency_ms=c.latency_ms, attempts=c.attempts)
                for c in results]}
        return guarded("checks", lambda: wf.run_checks(app), state, ok)

    def analyze(state: UnderwritingState):
        def work():
            case = wf.build_case(state["application"], state["income"],
                                 state["income_result"], state["checks"])
            return case, wf.run_analyzers(case)

        def ok(value, _):
            case, results = value
            return {"case": case, "audit": [
                _event("analysis", r.service, f"{len(r.signals)} signals",
                       metrics=r.metrics, signals=[s.code.value for s in r.signals],
                       # the audit is the restricted business record: evidence detail (which
                       # may name the applicant) lives here, not in prompts or traces
                       evidence={s.code.value: [e.detail for e in s.evidence]
                                 for s in r.signals if s.evidence})
                for r in results]}
        return guarded("analyze", work, state, ok)

    def policy(state: UnderwritingState):
        case = state["case"]

        def ok(result, _):
            if result is None:  # degraded: no citations, and the case says so
                result = AnalysisResult(service="policy_analysis", signals=[RiskSignal(
                    code=ReasonCode.WORKFLOW_ERROR, severity="info",
                    message="Policy retrieval unavailable; no citations attached.")])
            case.analyses.append(result)
            return {"case": case, "audit": [_event(
                "policy_retrieval", wf.policy_analyzer.name,
                f"{len(result.evidence)} citations",
                citations=[e.source for e in result.evidence])]}
        return guarded("policy", lambda: wf.policy_analyzer.analyze(case), state, ok)

    def agent(state: UnderwritingState):
        case = state["case"]

        def ok(proposal, _):
            if proposal is None:
                proposal = AgentRecommendation(
                    recommendation=Recommendation.MANUAL_REVIEW, valid=False,
                    rationale="Agent step failed; a human must decide.",
                    failure=ReasonCode.WORKFLOW_ERROR,
                    validation_errors=["agent node failed"])
            return {"proposal": proposal, "audit": [_event(
                "agent", f"agent:{proposal.model}",
                f"Proposed {proposal.recommendation.value}: {proposal.rationale}",
                prompt_version=proposal.prompt_version, attempts=proposal.attempts,
                valid=proposal.valid, validation_errors=proposal.validation_errors,
                input_tokens=proposal.input_tokens, output_tokens=proposal.output_tokens,
                tool_calls=proposal.tool_calls)]}
        return guarded("agent", lambda: wf.agent.recommend(case), state, ok)

    def engine(state: UnderwritingState):
        case, proposal = state["case"], state["proposal"]

        def ok(result, st):
            audit = st.get("audit", []) + [_event(
                "decision_engine", f"engine:{POLICY_VERSION}",
                f"Decided {result.recommendation.value}"
                + (" (overrode agent)" if result.overridden_by_policy else ""),
                findings=[f.model_dump(mode="json") for f in result.findings])]
            decision = UnderwritingDecision(
                application_id=case.application.application_id,
                recommendation=result.recommendation, reason_codes=result.reason_codes,
                agent_recommendation=proposal,
                overridden_by_policy=result.overridden_by_policy,
                requires_human_review=result.recommendation == Recommendation.MANUAL_REVIEW,
                metrics=case.metrics, audit_trail=audit)
            set_attrs(trace.get_current_span(),
                      decision__recommendation=result.recommendation.value,
                      decision__overridden=result.overridden_by_policy)
            return {"decision": decision, "audit": audit[-1:]}
        return guarded("engine", lambda: wf.engine.decide(case, proposal), state, ok)

    def escalate(state: UnderwritingState):
        """A required step failed: no engine decision is possible, so a human decides."""
        f = state["failure"]
        app = state["application"]
        case = state.get("case")
        event = _event("escalate", "workflow", f"Escalated: {f['node']} failed", **f)
        decision = UnderwritingDecision(
            application_id=app.application_id, recommendation=Recommendation.MANUAL_REVIEW,
            reason_codes=[ReasonCode.WORKFLOW_ERROR],
            agent_recommendation=state.get("proposal") or AgentRecommendation(
                recommendation=Recommendation.MANUAL_REVIEW, valid=False,
                rationale=f"Workflow stopped at {f['node']}; no proposal was made.",
                failure=ReasonCode.WORKFLOW_ERROR),
            overridden_by_policy=False, requires_human_review=True,
            metrics=case.metrics if case else {},
            audit_trail=state.get("audit", []) + [event])
        return {"decision": decision, "audit": [event]}

    def human_review(state: UnderwritingState):
        decision = state["decision"].model_copy(deep=True)
        case_id = wf.review_queue.submit(decision)
        decision.review_case_id = case_id
        events = [_event("human_review", "review_queue", f"Escalated as {case_id}")]
        if state.get("interactive"):
            answer = interrupt({
                "review_case_id": case_id,
                "application_id": decision.application_id,
                "reason_codes": [r.value for r in decision.reason_codes],
                "agent_proposal": decision.agent_recommendation.recommendation.value,
                "question": "APPROVE or DECLINE, with your reviewer id and a note",
            })
            review = HumanReview.model_validate(answer)
            decision.human_review = review
            events.append(_event("human_decision", f"human:{review.reviewer}",
                                 f"Reviewer decided {review.decision.value}: {review.note}"))
        decision.audit_trail = state.get("audit", []) + events
        return {"decision": decision, "audit": events}

    # -- edges ---------------------------------------------------------------------

    def next_or_escalate(nxt: str):
        return lambda state: "escalate" if state.get("failure") else nxt

    g = StateGraph(UnderwritingState)
    for name, fn in [("intake", intake), ("income", income), ("checks", checks),
                     ("analyze", analyze), ("policy", policy), ("agent", agent),
                     ("engine", engine), ("escalate", escalate),
                     ("human_review", human_review)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "income")
    for a, b in [("income", "checks"), ("checks", "analyze"), ("analyze", "policy")]:
        g.add_conditional_edges(a, next_or_escalate(b), [b, "escalate"])
    g.add_edge("policy", "agent")   # degrades, never escalates
    g.add_edge("agent", "engine")   # falls back, never escalates

    def after_engine(state: UnderwritingState) -> str:
        if state.get("failure"):
            return "escalate"
        return "human_review" if state["decision"].requires_human_review else END

    g.add_conditional_edges("engine", after_engine, ["escalate", "human_review", END])
    g.add_edge("escalate", "human_review")
    g.add_edge("human_review", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver(serde=_serde()))


def _serde() -> JsonPlusSerializer:
    """Checkpoints are deserialized on resume; allow exactly our domain types, nothing else."""
    import inspect
    from enum import Enum

    from pydantic import BaseModel

    from underwriter.domain import models

    allowed = [(models.__name__, name) for name, obj in vars(models).items()
               if inspect.isclass(obj) and obj.__module__ == models.__name__
               and issubclass(obj, BaseModel | Enum)]
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)
