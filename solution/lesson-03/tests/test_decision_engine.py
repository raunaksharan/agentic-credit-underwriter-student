"""The decision engine's contract: the agent may escalate, never relax policy."""

import pytest

from underwriter.decision.engine import DecisionEngine
from underwriter.domain.models import (
    AgentRecommendation,
    AnalysisResult,
    ReasonCode,
    Recommendation,
    UnderwritingCase,
    VerifiedIncome,
)
from underwriter.ingestion.documents import DATA_DIR, load_application

APP = load_application(DATA_DIR / "applications" / "APP-001.json")


def case_with(**metrics) -> UnderwritingCase:
    return UnderwritingCase(
        application=APP,
        verified_income=VerifiedIncome(monthly_gross_income=8000, method="payslip"),
        credit_profile=None,
        analyses=[AnalysisResult(service="test", metrics=metrics)],
    )


def proposal(rec: Recommendation) -> AgentRecommendation:
    return AgentRecommendation(recommendation=rec, rationale="test")


CLEAN = dict(credit_score=740, delinquencies_last_24m=0, post_loan_dti=0.20,
             income_discrepancy=0.0, loan_to_annual_income=0.15,
             employment_tenure_months=60)


@pytest.mark.parametrize(
    "overrides, expected, code",
    [
        ({}, Recommendation.APPROVE, ReasonCode.MEETS_ALL_CRITERIA),
        ({"post_loan_dti": 0.46}, Recommendation.MANUAL_REVIEW,
         ReasonCode.DTI_ABOVE_REVIEW_THRESHOLD),
        ({"post_loan_dti": 0.43}, Recommendation.APPROVE, ReasonCode.MEETS_ALL_CRITERIA),
        ({"post_loan_dti": 0.51}, Recommendation.DECLINE, ReasonCode.DTI_ABOVE_MAX),
        ({"credit_score": 579}, Recommendation.DECLINE, ReasonCode.CREDIT_SCORE_BELOW_MIN),
        ({"credit_score": 580}, Recommendation.MANUAL_REVIEW, ReasonCode.CREDIT_SCORE_REVIEW_BAND),
        ({"credit_score": 660}, Recommendation.APPROVE, ReasonCode.MEETS_ALL_CRITERIA),
        ({"income_discrepancy": 0.16}, Recommendation.MANUAL_REVIEW, ReasonCode.INCOME_MISMATCH),
        ({"delinquencies_last_24m": 1}, Recommendation.MANUAL_REVIEW,
         ReasonCode.RECENT_DELINQUENCY),
        ({"delinquencies_last_24m": 3}, Recommendation.DECLINE, ReasonCode.RECENT_DELINQUENCY),
        ({"employment_tenure_months": 4}, Recommendation.MANUAL_REVIEW,
         ReasonCode.EMPLOYMENT_TENURE_SHORT),
    ],
)
def test_policy_boundaries(overrides, expected, code):
    result = DecisionEngine().decide(case_with(**{**CLEAN, **overrides}),
                                     proposal(Recommendation.APPROVE))
    assert result.recommendation == expected
    assert code in result.reason_codes


def test_agent_cannot_relax_policy():
    result = DecisionEngine().decide(case_with(**{**CLEAN, "post_loan_dti": 0.46}),
                                     proposal(Recommendation.APPROVE))
    assert result.recommendation == Recommendation.MANUAL_REVIEW
    assert result.overridden_by_policy


def test_agent_may_escalate_to_human():
    result = DecisionEngine().decide(case_with(**CLEAN), proposal(Recommendation.MANUAL_REVIEW))
    assert result.recommendation == Recommendation.MANUAL_REVIEW
    assert not result.overridden_by_policy


def test_agent_decline_outside_policy_goes_to_human_not_decline():
    result = DecisionEngine().decide(case_with(**CLEAN), proposal(Recommendation.DECLINE))
    assert result.recommendation == Recommendation.MANUAL_REVIEW
    assert result.overridden_by_policy
