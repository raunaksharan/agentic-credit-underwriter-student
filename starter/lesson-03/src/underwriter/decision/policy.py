"""Policy thresholds, encoded from data/policies/unsecured_personal_lending_policy.md.

Lesson 1 design decision (ADR-0002): numeric policy rules live in code, versioned
and tested. Retrieval (lesson 2) lets the agent *explain* and *cite* policy, but
the thresholds that decide outcomes are never read out of an LLM's answer.
"""

from __future__ import annotations

from pydantic import BaseModel

POLICY_VERSION = "MDL-UPL-3.2"
POLICY_DOC = "policies/unsecured_personal_lending_policy.md"


class PolicyThresholds(BaseModel):
    min_credit_score_decline_below: int = 580  # 3.1
    min_credit_score_eligible: int = 660  # 3.2 / 3.3
    dti_review_above: float = 0.43  # 4.2
    dti_decline_above: float = 0.50  # 4.3
    income_mismatch_review_above: float = 0.15  # 5.4
    delinquencies_review_at: int = 1  # 6.1
    delinquencies_decline_at: int = 3  # 6.2
    max_loan_amount: float = 50_000  # 7.1
    max_loan_to_annual_income: float = 0.50  # 7.2
    min_tenure_months_salaried: int = 6  # 2.2
    min_tenure_months_self_employed: int = 24  # 2.3


DEFAULT_THRESHOLDS = PolicyThresholds()
