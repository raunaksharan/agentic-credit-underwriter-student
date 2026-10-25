"""End-to-end: every sample application reaches its expected outcome, with a full trace."""

import json

import pytest

from underwriter.domain.models import ReasonCode, Recommendation
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.pipeline.orchestrator import UnderwritingPipeline

EXPECTED = json.loads((DATA_DIR / "expected_outcomes.json").read_text())


@pytest.fixture(scope="module")
def pipeline():
    return UnderwritingPipeline()


def run(pipeline, app_id):
    return pipeline.run(load_application(DATA_DIR / "applications" / f"{app_id}.json"))


@pytest.mark.parametrize("app_id", sorted(EXPECTED))
def test_expected_outcome(pipeline, app_id):
    assert run(pipeline, app_id).recommendation.value == EXPECTED[app_id]["expected"]


def test_unavailable_credit_is_never_invented(pipeline):
    d = run(pipeline, "APP-003")
    assert "credit_score" not in d.metrics
    assert ReasonCode.CREDIT_DATA_UNAVAILABLE in d.reason_codes
    assert d.requires_human_review


def test_missing_income_document_blocks_dti(pipeline):
    d = run(pipeline, "APP-007")
    assert "post_loan_dti" not in d.metrics
    assert ReasonCode.MISSING_DOCUMENT in d.reason_codes


def test_engine_overrides_lenient_agent(pipeline):
    d = run(pipeline, "APP-008")
    assert d.agent_recommendation.recommendation == Recommendation.APPROVE
    assert d.recommendation == Recommendation.MANUAL_REVIEW
    assert d.overridden_by_policy


@pytest.mark.parametrize("app_id", sorted(EXPECTED))
def test_every_decision_is_auditable(pipeline, app_id):
    d = run(pipeline, app_id)
    steps = [e.step for e in d.audit_trail]
    assert steps[0] == "intake"
    assert "agent" in steps and "decision_engine" in steps
    assert d.agent_recommendation.evidence or d.requires_human_review
    if d.requires_human_review:
        assert steps[-1] == "human_review"
