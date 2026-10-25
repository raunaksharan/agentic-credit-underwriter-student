import pytest

from underwriter.risk.calculations import (
    debt_to_income,
    income_discrepancy,
    monthly_payment,
    post_loan_dti,
)


def test_monthly_payment_matches_amortization_formula():
    # 20,000 over 48 months at 14.9% APR
    assert monthly_payment(20_000, 0.149, 48) == pytest.approx(555.60, abs=0.01)


def test_zero_interest_payment_is_straight_line():
    assert monthly_payment(1_200, 0.0, 12) == pytest.approx(100.0)


def test_dti_is_a_fraction():
    assert debt_to_income(2_300, 5_000) == pytest.approx(0.46)


def test_post_loan_dti_includes_new_payment():
    assert post_loan_dti(1_800, 555.60, 5_166.67) == pytest.approx(0.4559, abs=1e-4)


def test_income_discrepancy_positive_when_overstated():
    # stated 120k, verified 7k/month = 84k  ->  ~43% overstated
    assert income_discrepancy(120_000, 7_000) == pytest.approx(0.4286, abs=1e-4)


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_income_raises(bad):
    with pytest.raises(ValueError):
        debt_to_income(100, bad)
