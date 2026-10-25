"""Lesson 5: the LangGraph workflow, per-node policies and the human-review edge."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from underwriter.agents.tool_agent import ToolUsingUnderwritingAgent
from underwriter.domain.models import HumanReview, ReasonCode, Recommendation
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.llm.mock import MockLLM
from underwriter.workflow.orchestrator import PendingReview, UnderwritingWorkflow
from underwriter.workflow.resilience import (
    NodeFailed,
    NodeFaults,
    NodePolicy,
    TransientNodeError,
    run_node,
)
from underwriter.workflow.services import InMemoryReviewQueue


def app(app_id: str):
    return load_application(DATA_DIR / "applications" / f"{app_id}.json")


def wf(node_fault: str | None = None, **kw) -> UnderwritingWorkflow:
    return UnderwritingWorkflow(agent=ToolUsingUnderwritingAgent(MockLLM()),
                                node_faults=NodeFaults.parse(node_fault), **kw)


def steps(decision) -> list[str]:
    return [e.step for e in decision.audit_trail]


REVIEW = {"reviewer": "u-1042", "decision": "APPROVE", "note": "Income confirmed by payroll."}


# -- run_node ------------------------------------------------------------------------


def test_run_node_retries_transient_errors_only():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise TransientNodeError("blip")
        return "ok"

    run = run_node("x", flaky, NodePolicy(timeout_s=1, max_attempts=2, backoff_s=0))
    assert run.value == "ok" and run.attempts == 2 and "blip" in run.errors[0]

    def bug():
        raise ValueError("bad input")

    with pytest.raises(NodeFailed) as exc:
        run_node("x", bug, NodePolicy(timeout_s=1, max_attempts=3))
    assert exc.value.attempts == 1  # a bug is not retried


def test_run_node_times_out():
    import time
    with pytest.raises(NodeFailed) as exc:
        run_node("x", lambda: time.sleep(0.3), NodePolicy(timeout_s=0.05, max_attempts=2,
                                                          backoff_s=0))
    assert exc.value.attempts == 2 and "timed out" in exc.value.reason


def test_node_faults_refused_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        NodeFaults.parse("income=error")
    with pytest.raises(ValueError):
        NodeFaults({"income": "explode"})


# -- the graph -----------------------------------------------------------------------


def test_graph_has_the_designed_shape():
    g = wf().graph.get_graph()
    edges = {(e.source, e.target) for e in g.edges}
    assert {"intake", "income", "checks", "analyze", "policy", "agent", "engine",
            "escalate", "human_review"} <= set(g.nodes)
    assert ("engine", "human_review") in edges and ("escalate", "human_review") in edges
    assert ("income", "escalate") in edges and ("policy", "escalate") not in edges


def test_audit_trail_runs_in_order_and_is_complete():
    d = wf().run(app("APP-002"))
    s = steps(d)
    assert s[:3] == ["intake", "income_verification", "check"]
    assert s.index("policy_retrieval") < s.index("agent") < s.index("decision_engine")
    assert s[-1] == "human_review" and d.review_case_id == "REV-APP-002"


def test_transient_failure_is_retried_and_logged():
    d = wf("income=transient").run(app("APP-001"))
    assert d.recommendation == Recommendation.APPROVE and "node_retry" in steps(d)


@pytest.mark.parametrize("node", ["income", "checks", "analyze", "engine"])
def test_required_node_failure_escalates(node):
    d = wf(f"{node}=error").run(app("APP-001"))
    assert d.recommendation == Recommendation.MANUAL_REVIEW
    assert d.reason_codes == [ReasonCode.WORKFLOW_ERROR]
    assert {"node_failure", "escalate", "human_review"} <= set(steps(d))


def test_node_timeout_escalates():
    d = wf("analyze=hang", node_policies={"analyze": NodePolicy(timeout_s=0.05)}).run(
        app("APP-001"))
    assert d.reason_codes == [ReasonCode.WORKFLOW_ERROR]
    assert "timed out" in next(e for e in d.audit_trail if e.step == "node_failure").summary


def test_policy_retrieval_degrades_and_says_so():
    d = wf("policy=error").run(app("APP-001"))
    assert d.recommendation == Recommendation.APPROVE  # thresholds don't depend on RAG (F8)
    failure = next(e for e in d.audit_trail if e.step == "node_failure")
    assert failure.data["on_failure"] == "degrade"
    retrieval = next(e for e in d.audit_trail if e.step == "policy_retrieval")
    assert retrieval.data["citations"] == []


def test_agent_failure_falls_back_and_the_engine_still_decides():
    d = wf("agent=error").run(app("APP-001"))
    assert not d.agent_recommendation.valid
    assert d.recommendation == Recommendation.MANUAL_REVIEW
    assert "decision_engine" in steps(d)
    assert wf("agent=error").run(app("APP-005")).recommendation == Recommendation.DECLINE


# -- the human-review edge -----------------------------------------------------------


def test_interactive_run_pauses_at_review_and_resumes():
    queue = InMemoryReviewQueue()
    w = wf(review_queue=queue)
    pending = w.start(app("APP-002"))
    assert isinstance(pending, PendingReview)
    assert pending.request["reason_codes"] == ["DTI_ABOVE_REVIEW_THRESHOLD"]
    assert "REV-APP-002" in queue.cases

    d = w.resume(pending.thread_id, HumanReview(**REVIEW))
    assert d.recommendation == Recommendation.MANUAL_REVIEW  # the engine's answer is kept
    assert d.final_recommendation == Recommendation.APPROVE  # the human's decision wins
    assert steps(d)[-2:] == ["human_review", "human_decision"]
    assert d.audit_trail[-1].actor == "human:u-1042"


def test_reviewer_can_decline():
    w = wf()
    pending = w.start(app("APP-006"))
    d = w.resume(pending.thread_id, HumanReview(**{**REVIEW, "decision": "DECLINE",
                                                   "note": "Identity not confirmed."}))
    assert d.final_recommendation == Recommendation.DECLINE


def test_review_must_be_complete():
    with pytest.raises(ValidationError):
        HumanReview(reviewer="", decision="APPROVE", note="ok then")
    with pytest.raises(ValidationError):
        HumanReview(reviewer="u-1", decision="MANUAL_REVIEW", note="can't decide")


def test_cases_that_need_no_review_never_pause():
    d = wf().start(app("APP-001"))
    assert not isinstance(d, PendingReview) and d.human_review is None
    assert wf().start(app("APP-005")).recommendation == Recommendation.DECLINE


def test_workflow_failure_can_still_be_reviewed():
    w = wf("checks=error")
    pending = w.start(app("APP-001"))
    assert pending.request["reason_codes"] == ["WORKFLOW_ERROR"]
    d = w.resume(pending.thread_id, HumanReview(**REVIEW))
    assert d.final_recommendation == Recommendation.APPROVE
