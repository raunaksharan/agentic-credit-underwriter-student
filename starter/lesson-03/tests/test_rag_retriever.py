"""Retriever behaviour: filters, versioning, abstain, citations, workflow wiring."""

from datetime import date

from underwriter.evaluation.retrieval import run_retrieval_eval
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.rag.retriever import PolicyRetriever, in_force, load_manifest
from underwriter.workflow.orchestrator import UnderwritingWorkflow

R = PolicyRetriever()
DOCS = {d.doc_id: d for d in load_manifest()}


def test_withdrawn_guidance_is_never_a_default_result():
    res = R.retrieve("explaining credit denials made by complex algorithms", k=10)
    assert not res.abstained
    assert all(r.chunk.status != "withdrawn" for r in res.results)


def test_research_mode_can_see_withdrawn_guidance():
    res = R.retrieve("explaining credit denials made by complex algorithms",
                     include_withdrawn=True)
    assert any(r.chunk.doc_id.startswith("cfpb-circular") for r in res.results)


def test_as_of_date_selects_the_version_in_force():
    q = "maximum debt-to-income ratio for a qualified mortgage"
    today = {r.chunk.doc_id for r in R.retrieve(q, k=10).results}
    then = {r.chunk.doc_id for r in R.retrieve(q, k=10, as_of=date(2020, 6, 1)).results}
    assert "reg-z-1026.43-2020" not in today
    assert "reg-z-1026.43-current" not in then


def test_in_force_rules():
    assert not in_force(DOCS["cfpb-circular-2022-03"], DOCS, date(2026, 1, 1))
    assert in_force(DOCS["cfpb-circular-2022-03"], DOCS, date(2023, 1, 1))
    assert in_force(DOCS["reg-z-1026.43-2020"], DOCS, date(2020, 6, 1))
    assert not in_force(DOCS["reg-z-1026.43-2020"], DOCS, date(2022, 1, 1))


def test_off_topic_question_abstains():
    res = R.retrieve("best pasta recipe with fresh tomatoes")
    assert res.abstained and res.results == []
    assert "No applicable policy" in res.reason


def test_source_type_filter():
    res = R.retrieve("credit score", source_types={"internal_policy"})
    assert {r.chunk.source_type for r in res.results} == {"internal_policy"}


def test_retrieval_eval_meets_baseline():
    report = run_retrieval_eval(R)
    assert report.hit_at_5 >= 0.94
    assert report.abstain_accuracy == 1.0
    assert report.stale_citations == 0


def test_workflow_decisions_cite_retrieved_policy():
    app = load_application(DATA_DIR / "applications" / "APP-002.json")
    d = UnderwritingWorkflow().run(app)
    cited = [e.source for e in d.agent_recommendation.evidence]
    assert "mdl-upl-policy-3.2#4" in cited  # the DTI section
    assert any(e.step == "policy_retrieval" for e in d.audit_trail)
