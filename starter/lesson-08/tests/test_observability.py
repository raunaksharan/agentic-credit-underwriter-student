"""Lesson 7: traces, GenAI token attributes, usage metering, and no PII in telemetry."""

from __future__ import annotations

import pytest
from opentelemetry.trace import StatusCode

from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.llm.client import LLMUnavailable, Message
from underwriter.llm.config import get_llm_client
from underwriter.observability import metering
from underwriter.observability.metering import UsageMeter
from underwriter.observability.metering import metering as meter_ctx
from underwriter.observability.report import render_tree
from underwriter.observability.tracing import memory_exporter
from underwriter.tools.faults import FaultPlan
from underwriter.workflow.orchestrator import UnderwritingWorkflow
from underwriter.workflow.resilience import NodeFaults

APPS = [f"APP-00{i}" for i in range(1, 9)]


def app(app_id: str):
    return load_application(DATA_DIR / "applications" / f"{app_id}.json")


@pytest.fixture
def spans():
    mem = memory_exporter()
    mem.clear()
    yield mem
    mem.clear()


def run(app_id="APP-002", **kw):
    return UnderwritingWorkflow(**kw).run(app(app_id))


def tree(mem):
    s = mem.get_finished_spans()
    by_id = {x.context.span_id: x for x in s}
    parent = {x.name: (by_id[x.parent.span_id].name if x.parent else None) for x in s}
    return s, parent


def test_one_root_span_per_decision_and_every_span_under_it(spans):
    run()
    s, parent = tree(spans)
    roots = [x for x in s if x.parent is None]
    assert [r.name for r in roots] == ["underwrite APP-002"]
    assert {f"node {n}" for n in ("income", "checks", "analyze", "policy", "agent", "engine")} \
        <= set(parent)
    assert parent["check credit_bureau"] == "node checks"     # context reached the worker thread
    assert parent["chat mock-underwriter-v1"] == "node agent"
    assert parent["tool check_policy"] == "node agent"


def test_genai_token_attributes_add_up_to_the_decision(spans):
    d = run()
    chats = [x for x in spans.get_finished_spans() if x.name.startswith("chat ")]
    tokens_in = sum(x.attributes["gen_ai.usage.input_tokens"] for x in chats)
    assert chats and all(x.attributes["gen_ai.operation.name"] == "chat" for x in chats)
    assert tokens_in == d.usage.input_tokens == d.agent_recommendation.input_tokens
    assert d.usage.llm_calls == len(chats) == d.agent_recommendation.attempts


def test_failures_are_error_spans(spans):
    run("APP-001", faults=FaultPlan.parse("bank_data=server_error"))
    bank = next(x for x in spans.get_finished_spans() if x.name == "check bank_data")
    assert bank.status.status_code == StatusCode.ERROR
    assert bank.attributes["check.status"] == "UNAVAILABLE"

    spans.clear()
    run("APP-001", node_faults=NodeFaults.parse("income=error"))
    node = next(x for x in spans.get_finished_spans() if x.name == "node income")
    assert node.status.status_code == StatusCode.ERROR
    assert node.attributes["node.outcome"] == "escalate"


def test_retries_are_visible_on_the_node_span(spans):
    run("APP-001", node_faults=NodeFaults.parse("income=transient"))
    node = next(x for x in spans.get_finished_spans() if x.name == "node income")
    assert node.attributes["node.attempts"] == 2 and node.attributes["node.outcome"] == "retried"


def test_model_outage_marks_the_chat_span(spans):
    client = get_llm_client(fault="unavailable")
    with pytest.raises(LLMUnavailable):
        client.complete([Message(role="user", content="hi")])
    chat = spans.get_finished_spans()[-1]
    assert chat.status.status_code == StatusCode.ERROR
    assert chat.attributes["error.type"] == "LLMUnavailable"


@pytest.mark.parametrize("app_id", APPS)
def test_no_personal_data_in_any_span(spans, app_id):
    a = app(app_id)
    run(app_id)
    secrets = {a.applicant.full_name, a.applicant.email, a.applicant.national_id_last4,
               str(a.applicant.date_of_birth), *a.applicant.full_name.split()}
    for s in spans.get_finished_spans():
        for key, value in s.attributes.items():
            text = " ".join(value) if isinstance(value, tuple) else str(value)
            leaked = [x for x in secrets if len(x) >= 4 and x in text]
            assert not leaked, f"{s.name} {key} contains {leaked}"


def test_usage_is_per_decision_and_has_step_times():
    wf = UnderwritingWorkflow()
    a, b = wf.run(app("APP-002")), wf.run(app("APP-005"))
    assert a.usage is not b.usage
    assert a.usage.llm_calls >= 1 and b.usage.llm_calls >= 1
    assert set(a.usage.step_ms) >= {"income", "checks", "agent", "engine"}
    assert a.usage.total_ms >= sum(a.usage.step_ms.values()) * 0.9


def test_cost_uses_the_price_table(monkeypatch):
    monkeypatch.setitem(metering.PRICES, "priced-model", (3.0, 15.0))
    m = UsageMeter()
    assert m.record_llm("priced-model", 1_000_000, 100_000) == pytest.approx(4.5)
    assert m.usage.cost_known
    m.record_llm("unpriced-model", 10, 10)
    assert not m.usage.cost_known and m.usage.cost_usd == pytest.approx(4.5)


def test_no_meter_outside_a_run_is_fine():
    assert metering.current_meter() is None
    with meter_ctx() as m:
        assert metering.current_meter() is m
    assert metering.current_meter() is None


def test_trace_tree_renders(spans):
    run()
    text = render_tree(spans.get_finished_spans())
    assert text.splitlines()[0].startswith("underwrite APP-002")
    assert "└─ node engine" in text and "in=" in text


def test_exception_text_in_spans_is_redacted(spans):
    from underwriter.observability.tracing import redact, span
    with pytest.raises(ValueError), span("boom"):
        raise ValueError("no record for applicant 5562, contact jane1234@example.com")
    s = spans.get_finished_spans()[-1]
    assert s.status.status_code == StatusCode.ERROR
    assert "5562" not in s.status.description and "example.com" not in s.status.description
    assert s.attributes["error.type"] == "ValueError"
    assert not s.events          # no raw exception event or stack trace
    assert redact("jane1234@example.com and 123456") == "<email> and <digits>"
