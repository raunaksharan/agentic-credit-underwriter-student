"""Lesson 3: the LLM port, context engineering, structured output and validation."""

import json

import pytest

from underwriter.agents.context import build_context
from underwriter.agents.underwriting import PROMPT_VERSION, LLMUnderwritingAgent, build_messages
from underwriter.agents.validation import UnderwritingOutput, parse_output, semantic_errors
from underwriter.domain.models import ReasonCode, Recommendation
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.llm.config import get_llm_client
from underwriter.llm.mock import MockLLM
from underwriter.workflow.orchestrator import UnderwritingWorkflow


def case(app_id):
    app = load_application(DATA_DIR / "applications" / f"{app_id}.json")
    return UnderwritingWorkflow().assemble_case(app)[0]


def run(app_id, fault=None):
    wf = UnderwritingWorkflow(agent=LLMUnderwritingAgent(MockLLM(fault=fault)))
    return wf.run(load_application(DATA_DIR / "applications" / f"{app_id}.json"))


# -- context engineering ------------------------------------------------------

def test_context_excludes_personal_data():
    text = build_context(case("APP-001")).as_json
    for pii in ("Priya", "Raman", "4821", "priya.raman@example.com", "Alder Court", "1990-03-14"):
        assert pii not in text


@pytest.mark.parametrize("app_id", [f"APP-00{i}" for i in range(1, 9)])
def test_no_application_leaks_personal_data_into_context(app_id):
    # lesson 7 found the id digits leaking through a bureau error message on APP-003
    c = case(app_id)
    a = c.application.applicant
    text = build_context(c).as_json
    for pii in (a.full_name, *a.full_name.split(), a.email, a.national_id_last4,
                str(a.date_of_birth)):
        assert pii not in text, f"{app_id}: {pii!r} reached the model context"


def test_every_context_item_is_citable():
    ctx = build_context(case("APP-006"))
    payload = ctx.payload
    ids = [m["id"] for m in payload["metrics"].values()] + [s["id"] for s in payload["signals"]]
    ids += [p["id"] for p in payload["policy"]] + [d["id"] for d in payload["documents"]]
    assert set(ids) == set(ctx.allowed_ids)


def test_context_respects_budget_by_dropping_policy_last():
    ctx = build_context(case("APP-006"), max_chars=2500)
    assert len(ctx.as_json) <= 2500 or not ctx.payload["policy"]
    assert ctx.dropped_policy > 0
    assert ctx.payload["signals"]  # signals are never dropped


def test_prompt_carries_version_and_case():
    messages, _ = build_messages(case("APP-002"))
    assert messages[0].role == "system" and "PROPOSE" in messages[0].content
    assert "<case_json>" in messages[1].content
    assert PROMPT_VERSION == "underwriting-v1"


# -- structured output and validators ----------------------------------------

def test_parse_tolerates_fences_and_chatter():
    out = parse_output('Here you go:\n```json\n{"recommendation": "APPROVE", "rationale": "ok", '
                       '"evidence": ["metric:credit_score"]}\n```')
    assert out.recommendation == "APPROVE"


@pytest.mark.parametrize("text", ["not json", '{"recommendation": "MAYBE", "rationale": "x", '
                                  '"evidence": ["a"]}', '{"recommendation": "APPROVE"}'])
def test_parse_rejects_bad_shapes(text):
    with pytest.raises(ValueError):
        parse_output(text)


def test_semantic_validators_catch_content_errors():
    ctx = build_context(case("APP-002"))
    bad = UnderwritingOutput(recommendation="APPROVE", rationale="DTI is 30.0%.",
                             evidence=["policy:made-up"], figures={"post_loan_dti": 0.30},
                             missing_information=["bank statement"])
    errors = " | ".join(semantic_errors(bad, ctx))
    assert "not in the context" in errors
    assert "figures.post_loan_dti" in errors
    assert "30.0%" in errors
    assert "missing" in errors


def test_threshold_quoted_from_policy_is_allowed():
    ctx = build_context(case("APP-002"))
    ok = UnderwritingOutput(recommendation="MANUAL_REVIEW",
                            rationale="DTI of 45.6% is above the 43% review threshold.",
                            evidence=["metric:post_loan_dti"], figures={"post_loan_dti": 0.4559})
    assert semantic_errors(ok, ctx) == []


# -- the agent end to end -----------------------------------------------------

def test_valid_answer_on_first_attempt():
    d = run("APP-002")
    p = d.agent_recommendation
    assert p.valid and p.attempts == 1 and p.prompt_version == PROMPT_VERSION
    assert p.input_tokens > 0 and p.output_tokens > 0
    assert any(e.source == "metric:post_loan_dti" for e in p.evidence)


@pytest.mark.parametrize("fault", ["malformed", "bad_citation", "wrong_number"])
def test_one_repair_fixes_a_one_off_fault(fault):
    p = run("APP-002", fault).agent_recommendation
    assert p.valid and p.attempts == 2


@pytest.mark.parametrize("fault", ["malformed_always", "bad_citation_always",
                                   "wrong_number_always"])
def test_persistent_bad_output_goes_to_a_human(fault):
    d = run("APP-001", fault)
    assert d.recommendation == Recommendation.MANUAL_REVIEW
    assert ReasonCode.INVALID_MODEL_OUTPUT in d.reason_codes
    assert not d.agent_recommendation.valid and d.agent_recommendation.attempts == 2


def test_provider_outage_goes_to_a_human_without_retrying():
    d = run("APP-001", "unavailable")
    assert ReasonCode.MODEL_UNAVAILABLE in d.reason_codes
    assert d.agent_recommendation.attempts == 1


def test_policy_decline_stands_when_the_model_fails():
    assert run("APP-005", "malformed_always").recommendation == Recommendation.DECLINE


def test_audit_records_model_and_prompt():
    d = run("APP-002")
    agent_event = next(e for e in d.audit_trail if e.step == "agent")
    assert agent_event.data["prompt_version"] == PROMPT_VERSION
    assert agent_event.actor == "agent:mock-underwriter-v1"


# -- configuration ------------------------------------------------------------

def test_default_mode_is_mock(monkeypatch):
    monkeypatch.delenv("LLM_MODE", raising=False)
    client = get_llm_client()
    # lesson 7 wraps every client for tracing; the model underneath is still the mock
    assert isinstance(getattr(client, "inner", client), MockLLM)


def test_live_mode_requires_a_model(monkeypatch):
    from underwriter.llm.client import LLMUnavailable
    monkeypatch.setenv("LLM_MODE", "live")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(LLMUnavailable):
        get_llm_client()


def test_mock_is_deterministic():
    a = MockLLM().complete(build_messages(case("APP-001"))[0])
    b = MockLLM().complete(build_messages(case("APP-001"))[0])
    assert a.text == b.text and json.loads(a.text)["recommendation"] == "APPROVE"
