"""Deterministic decision engine.

The engine does two things:
1. Evaluates the policy against the case's verified facts (metrics + signals).
2. Reconciles that with the agent's proposal under one rule:
   **the agent may escalate, it may never relax policy.**
"""

from __future__ import annotations

from pydantic import BaseModel

from underwriter.decision.policy import DEFAULT_THRESHOLDS, PolicyThresholds
from underwriter.domain.models import (
    AgentRecommendation,
    ReasonCode,
    Recommendation,
    UnderwritingCase,
)

_SEVERITY_RANK = {Recommendation.APPROVE: 0, Recommendation.MANUAL_REVIEW: 1,
                  Recommendation.DECLINE: 2}


class PolicyFinding(BaseModel):
    code: ReasonCode
    outcome: Recommendation
    section: str
    message: str


class EngineResult(BaseModel):
    recommendation: Recommendation
    findings: list[PolicyFinding]
    overridden_by_policy: bool

    @property
    def reason_codes(self) -> list[ReasonCode]:
        if not self.findings:
            return [ReasonCode.MEETS_ALL_CRITERIA]
        return list(dict.fromkeys(f.code for f in self.findings))


class DecisionEngine:
    def __init__(self, thresholds: PolicyThresholds = DEFAULT_THRESHOLDS) -> None:
        self.t = thresholds

    # -- 1. policy evaluation -------------------------------------------------

    def evaluate_policy(self, case: UnderwritingCase) -> list[PolicyFinding]:
        t, m = self.t, case.metrics
        findings: list[PolicyFinding] = []

        def add(code: ReasonCode, outcome: Recommendation, section: str, msg: str) -> None:
            findings.append(PolicyFinding(code=code, outcome=outcome, section=section,
                                          message=msg))

        # Data-quality and fraud signals raised by analysis services always need a human.
        for s in case.all_signals:
            if s.severity in ("review", "decline"):
                add(s.code, Recommendation.MANUAL_REVIEW, "9.1", s.message)

        score = m.get("credit_score")
        if score is not None:
            if score < t.min_credit_score_decline_below:
                add(ReasonCode.CREDIT_SCORE_BELOW_MIN, Recommendation.DECLINE, "3.1",
                    f"Credit score {score:.0f} is below {t.min_credit_score_decline_below}.")
            elif score < t.min_credit_score_eligible:
                add(ReasonCode.CREDIT_SCORE_REVIEW_BAND, Recommendation.MANUAL_REVIEW, "3.2",
                    f"Credit score {score:.0f} is in the review band.")

        delinq = m.get("delinquencies_last_24m")
        if delinq is not None:
            if delinq >= t.delinquencies_decline_at:
                add(ReasonCode.RECENT_DELINQUENCY, Recommendation.DECLINE, "6.2",
                    f"{delinq:.0f} delinquencies in the last 24 months.")
            elif delinq >= t.delinquencies_review_at:
                add(ReasonCode.RECENT_DELINQUENCY, Recommendation.MANUAL_REVIEW, "6.1",
                    f"{delinq:.0f} delinquencies in the last 24 months.")

        dti = m.get("post_loan_dti")
        if dti is not None:
            if dti > t.dti_decline_above:
                add(ReasonCode.DTI_ABOVE_MAX, Recommendation.DECLINE, "4.3",
                    f"Post-loan DTI {dti:.1%} exceeds {t.dti_decline_above:.0%}.")
            elif dti > t.dti_review_above:
                add(ReasonCode.DTI_ABOVE_REVIEW_THRESHOLD, Recommendation.MANUAL_REVIEW, "4.2",
                    f"Post-loan DTI {dti:.1%} is above {t.dti_review_above:.0%}.")

        gap = m.get("income_discrepancy")
        if gap is not None and gap > t.income_mismatch_review_above:
            add(ReasonCode.INCOME_MISMATCH, Recommendation.MANUAL_REVIEW, "5.4",
                f"Stated income exceeds verified income by {gap:.0%}.")

        amount = case.application.loan.amount
        if amount > t.max_loan_amount:
            add(ReasonCode.LOAN_AMOUNT_ABOVE_LIMIT, Recommendation.DECLINE, "7.1",
                f"Requested {amount:,.0f} exceeds the product maximum.")
        lti = m.get("loan_to_annual_income")
        if lti is not None and lti > t.max_loan_to_annual_income:
            add(ReasonCode.LOAN_AMOUNT_ABOVE_LIMIT, Recommendation.MANUAL_REVIEW, "7.2",
                f"Loan is {lti:.0%} of verified annual income.")

        tenure = m.get("employment_tenure_months")
        if tenure is not None:
            self_employed = case.application.employment.employment_type == "self_employed"
            minimum = (t.min_tenure_months_self_employed if self_employed
                       else t.min_tenure_months_salaried)
            if tenure < minimum:
                add(ReasonCode.EMPLOYMENT_TENURE_SHORT, Recommendation.MANUAL_REVIEW,
                    "2.3" if self_employed else "2.2",
                    f"{tenure:.0f} months in current employment; policy minimum is {minimum}.")

        return findings

    # -- 2. reconciliation ----------------------------------------------------

    def decide(self, case: UnderwritingCase, proposal: AgentRecommendation) -> EngineResult:
        findings = self.evaluate_policy(case)
        if not proposal.valid:
            # The model failed (unparseable, uncited, wrong numbers, or down). Its proposal is
            # not evidence of anything, so a human decides. Policy declines still stand.
            findings.append(PolicyFinding(
                code=proposal.failure or ReasonCode.INVALID_MODEL_OUTPUT,
                outcome=Recommendation.MANUAL_REVIEW, section="9.1",
                message="Agent output unusable: " + "; ".join(proposal.validation_errors[:3])))
        policy_outcome = max(
            (f.outcome for f in findings), key=_SEVERITY_RANK.__getitem__,
            default=Recommendation.APPROVE,
        )
        agent = proposal.recommendation

        if _SEVERITY_RANK[agent] >= _SEVERITY_RANK[policy_outcome]:
            # Agent is as strict or stricter than policy. It may escalate to a human,
            # but it may not decline something policy would not decline.
            final = Recommendation.MANUAL_REVIEW if (
                agent == Recommendation.DECLINE and policy_outcome != Recommendation.DECLINE
            ) else agent
        else:
            final = policy_outcome  # agent tried to relax policy: policy wins

        return EngineResult(
            recommendation=final,
            findings=findings,
            overridden_by_policy=final != agent,
        )
