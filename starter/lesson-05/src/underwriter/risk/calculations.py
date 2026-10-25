"""Deterministic financial calculations.

These are deliberately NOT done by an LLM. They must be exact, reproducible
and unit-tested; an agent may *call* them as tools (lesson 4) but never
estimate them.
"""

from __future__ import annotations


def monthly_payment(principal: float, annual_rate: float, term_months: int) -> float:
    """Standard amortizing loan payment."""
    if principal <= 0 or term_months <= 0:
        raise ValueError("principal and term_months must be positive")
    r = annual_rate / 12
    if r == 0:
        return principal / term_months
    return principal * r / (1 - (1 + r) ** -term_months)


def debt_to_income(monthly_debt: float, monthly_gross_income: float) -> float:
    """DTI as a fraction (0.46 == 46%)."""
    if monthly_gross_income <= 0:
        raise ValueError("monthly_gross_income must be positive")
    return monthly_debt / monthly_gross_income


def post_loan_dti(
    existing_monthly_debt: float,
    new_payment: float,
    monthly_gross_income: float,
) -> float:
    """DTI after the requested loan is added. This is the number policy cares about."""
    return debt_to_income(existing_monthly_debt + new_payment, monthly_gross_income)


def income_discrepancy(stated_annual: float, verified_monthly: float) -> float:
    """Relative gap between what the applicant said and what documents show.
    Positive means the applicant overstated income."""
    verified_annual = verified_monthly * 12
    if verified_annual <= 0:
        raise ValueError("verified income must be positive")
    return (stated_annual - verified_annual) / verified_annual
