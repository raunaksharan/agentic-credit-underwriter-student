"""Lesson 6: the eval harness must pass on the real system and fail on a broken one."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from underwriter.decision import engine as engine_mod
from underwriter.decision.policy import PolicyThresholds
from underwriter.domain.models import Recommendation
from underwriter.evaluation import harness
from underwriter.evaluation.harness import (
    CASES,
    EvalReport,
    invariant_violations,
    load_cases,
    run_case,
    run_eval,
)

KNOWN_TAGS = {"baseline", "llm", "agent", "tools", "workflow", "safety"}


@pytest.fixture(scope="module")
def report() -> EvalReport:
    return run_eval()


def test_golden_cases_are_well_formed():
    cases = load_cases()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)) >= 30
    assert all(set(c.tags) <= KNOWN_TAGS for c in cases)
    assert {"baseline", "llm", "agent", "tools", "workflow"} <= {t for c in cases for t in c.tags}
    raw = json.loads(CASES.read_text())["cases"]
    assert all(c["scenario"] for c in raw)


def test_the_real_system_passes_every_gate(report):
    m = report.metrics()
    assert report.passed, report.markdown()
    assert m["unsafe_approvals"] == 0 and m["unfair_declines"] == 0
    assert m["pass_rate"] == 1.0


def test_every_failure_family_is_exercised(report):
    by_tag = report.by_tag()
    assert all(n >= 5 for _, (_, n) in by_tag.items() if _ != "safety")


def test_invariants_flag_an_unsafe_approval():
    outcome_decision = None
    case = next(c for c in load_cases() if c.id == "G-B02")  # expected MANUAL_REVIEW
    from underwriter.ingestion.documents import DATA_DIR, load_application
    from underwriter.workflow.orchestrator import UnderwritingWorkflow
    outcome_decision = UnderwritingWorkflow().run(
        load_application(DATA_DIR / "applications" / f"{case.application}.json"))
    forged = outcome_decision.model_copy(update={"recommendation": Recommendation.APPROVE,
                                                 "requires_human_review": False})
    v = invariant_violations(forged, Recommendation.MANUAL_REVIEW)
    assert any(x.startswith("UNSAFE_APPROVAL") for x in v)


def test_a_loosened_policy_is_caught():
    def loose(self, thresholds=None):
        self.t = PolicyThresholds(dti_review_above=0.47)

    with mock.patch.object(engine_mod.DecisionEngine, "__init__", loose):
        broken = run_eval(tag="baseline")
    assert not broken.passed
    assert broken.metrics()["unsafe_approvals"] >= 1
    assert {"G-B02", "G-B08"} <= {c.id for c in broken.outcomes if not c.passed}


def test_a_case_that_expects_too_much_fails_clearly():
    case = next(c for c in load_cases() if c.id == "G-B01")
    wrong = case.model_copy(update={"expect": case.expect.model_copy(
        update={"recommendation": Recommendation.DECLINE})})
    out = run_case(wrong)
    assert not out.passed and "expected DECLINE" in out.failures[0]


def test_token_regression_against_baseline_fails_the_gate(report):
    base = {**report.metrics(), "mean_input_tokens": report.metrics()["mean_input_tokens"] / 2}
    regressed = report.model_copy(update={"baseline": base})
    gates = {n: ok for n, ok, _ in regressed.gate_results()}
    assert gates["tokens vs baseline"] is False and not regressed.passed


def test_markdown_report_lists_gates_and_failures(report):
    md = report.markdown()
    assert "| unsafe approvals | pass |" in md and "| pass_rate | 1.0 |" in md


def test_baseline_file_matches_the_suite(report):
    base = json.loads(harness.BASELINE.read_text())
    assert base["cases"] == report.metrics()["cases"]
