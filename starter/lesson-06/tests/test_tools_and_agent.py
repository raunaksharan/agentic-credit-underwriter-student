"""Lesson 4: typed external checks, fault injection and the bounded tool-calling agent."""

from __future__ import annotations

import itertools

import pytest

from underwriter.agents.tool_agent import ToolUsingUnderwritingAgent, parse_action
from underwriter.agents.tools import build_toolbox
from underwriter.domain.models import CheckStatus, ReasonCode, Recommendation
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.llm.mock import MockLLM
from underwriter.tools.checks import CHECKS, run_check, run_checks
from underwriter.tools.faults import FaultPlan
from underwriter.workflow.orchestrator import UnderwritingWorkflow


def app(app_id: str):
    return load_application(DATA_DIR / "applications" / f"{app_id}.json")


def run(app_id: str, *, llm_fault: str | None = None, tool_fault: str | None = None, **kw):
    agent = ToolUsingUnderwritingAgent(MockLLM(fault=llm_fault), **kw)
    return UnderwritingWorkflow(agent=agent, faults=FaultPlan.parse(tool_fault)).run(app(app_id))


# -- fault plans ---------------------------------------------------------------------


def test_fault_plan_parses_and_rejects_unknown_kinds():
    plan = FaultPlan.parse("credit_bureau=timeout, bank_data=latency:50")
    assert plan.for_tool("credit_bureau") == "timeout"
    assert plan.latency_ms("bank_data") == 50
    with pytest.raises(ValueError):
        FaultPlan.parse("credit_bureau=explode")


def test_fault_injection_is_refused_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        FaultPlan.parse("credit_bureau=timeout")
    assert FaultPlan.parse("").faults == {}  # no faults is fine anywhere


# -- typed checks --------------------------------------------------------------------


def test_every_check_returns_a_typed_result_never_none():
    results = run_checks(app("APP-001"))
    assert [r.tool for r in results] == [c.name for c in CHECKS]
    assert all(r.status == CheckStatus.OK for r in results)


@pytest.mark.parametrize("kind,status", [
    ("timeout", CheckStatus.UNAVAILABLE), ("rate_limit", CheckStatus.UNAVAILABLE),
    ("server_error", CheckStatus.UNAVAILABLE), ("malformed", CheckStatus.INVALID),
])
def test_faults_map_to_statuses(kind, status):
    spec = next(c for c in CHECKS if c.name == "credit_bureau")
    r = run_check(spec, app("APP-001"), FaultPlan({"credit_bureau": kind}))
    assert r.status == status and r.reason and r.data == {}


def test_no_bureau_record_is_unavailable_not_a_crash():
    spec = next(c for c in CHECKS if c.name == "credit_bureau")
    assert run_check(spec, app("APP-003")).status == CheckStatus.UNAVAILABLE


@pytest.mark.parametrize("fault,expected,code", [
    ("credit_bureau=timeout", "MANUAL_REVIEW", ReasonCode.CREDIT_DATA_UNAVAILABLE),
    ("credit_bureau=malformed", "MANUAL_REVIEW", ReasonCode.CREDIT_DATA_UNAVAILABLE),
    ("fraud_screen=server_error", "MANUAL_REVIEW", ReasonCode.CHECK_UNAVAILABLE),
    ("bank_data=server_error", "APPROVE", None),          # optional check: carry on
    ("employment_verification=timeout", "APPROVE", None),
])
def test_required_vs_optional_checks(fault, expected, code):
    d = run("APP-001", tool_fault=fault)
    assert d.recommendation.value == expected
    if code:
        assert code in d.reason_codes


def test_a_tool_outage_never_turns_a_decline_into_an_approve():
    d = run("APP-005", tool_fault="fraud_screen=timeout,bank_data=timeout")
    assert d.recommendation == Recommendation.DECLINE


# -- the tool box --------------------------------------------------------------------


def test_toolbox_refuses_unknown_tools_and_bad_arguments():
    wf = UnderwritingWorkflow(agent=ToolUsingUnderwritingAgent(MockLLM()))
    case, _ = wf.assemble_case(app("APP-001"))
    box = build_toolbox(case, ToolUsingUnderwritingAgent(MockLLM()).retriever)
    ok, res = box.call("approve_loan", {})
    assert not ok and "not allowed" in res["error"]
    ok, res = box.call("request_missing_document", {"doc_type": "selfie", "reason": "x"})
    assert not ok and "bad arguments" in res["error"]
    ok, res = box.call("check_policy", {"query": "debt-to-income ratio"})
    assert ok and res["results"] and res["results"][0]["id"] in box.new_ids


def test_parse_action_requires_a_known_action():
    assert parse_action('{"action": "final", "answer": {}}')["action"] == "final"
    with pytest.raises(ValueError):
        parse_action('{"action": "approve"}')


# -- the bounded agent ---------------------------------------------------------------


def test_agent_uses_tools_and_cites_their_results():
    d = run("APP-002")
    p = d.agent_recommendation
    assert p.valid and [c["tool"] for c in p.tool_calls] == ["check_policy"]
    assert any(e.source.startswith("cfr") or "#" in e.source for e in p.evidence)


def test_agent_requests_the_missing_document():
    p = run("APP-007").agent_recommendation
    assert p.tool_calls[0]["tool"] == "request_missing_document"
    assert p.tool_calls[0]["arguments"]["doc_type"] == "tax_return"
    assert p.recommendation == Recommendation.MANUAL_REVIEW


def test_step_cap_stops_a_looping_agent():
    d = run("APP-001", llm_fault="loop")
    p = d.agent_recommendation
    assert len(p.tool_calls) == 4 and not p.valid
    assert p.failure == ReasonCode.AGENT_LIMIT_REACHED
    assert d.recommendation == Recommendation.MANUAL_REVIEW


def test_deadline_stops_the_agent():
    ticks = itertools.count(0, 10)  # every clock read is 10 s later
    d = run("APP-001", deadline_s=15, clock=lambda: next(ticks))
    assert d.agent_recommendation.failure == ReasonCode.AGENT_LIMIT_REACHED
    assert "deadline" in d.agent_recommendation.validation_errors[0]


def test_disallowed_tool_is_refused_and_the_agent_recovers():
    p = run("APP-001", llm_fault="disallowed_tool").agent_recommendation
    assert p.tool_calls[0] == {"tool": "approve_loan", "arguments": {"application_id": "APP-001"},
                               "outcome": "rejected", "detail": p.tool_calls[0]["detail"]}
    assert p.valid and p.recommendation == Recommendation.APPROVE


@pytest.mark.parametrize("fault,valid", [("malformed", True), ("bad_citation", True),
                                         ("malformed_always", False), ("unavailable", False)])
def test_final_answer_is_validated_and_repaired_once(fault, valid):
    d = run("APP-001", llm_fault=fault)
    assert d.agent_recommendation.valid is valid
    assert d.recommendation == (Recommendation.APPROVE if valid else Recommendation.MANUAL_REVIEW)


def test_policy_decline_stands_even_when_the_agent_fails():
    assert run("APP-005", llm_fault="loop").recommendation == Recommendation.DECLINE
