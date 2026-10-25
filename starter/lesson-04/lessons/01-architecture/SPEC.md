# Lesson 1 spec: exact calculations and the decision engine

**You build:** `src/underwriter/risk/calculations.py` and `src/underwriter/decision/engine.py`.

**Given (the seed):**
- `domain/models.py` (types and reason codes) and `decision/policy.py` (thresholds,
  which are business commitments);
- `workflow/contracts.py` and `workflow/services.py` (document intake, the analyzers,
  the rules agent stub, the review queue);
- `workflow/orchestrator.py`, the CLI, and all of `data/`.

**Answer key:** `tests/test_calculations.py`, `tests/test_decision_engine.py`,
`tests/test_workflow.py`, and `uv run underwriter run-all` (8/8 against
`data/expected_outcomes.json`).

**At the start:** both modules hold only their docstring, so every test file errors at
import, apart from `test_data_contracts.py`.

```bash
uv run pytest --continue-on-collection-errors
uv run pytest tests/test_calculations.py        # module 1
uv run pytest tests/test_decision_engine.py     # module 2
uv run underwriter run-all                         # the system, end to end
```

## `risk/calculations.py`: exact arithmetic, never a model's estimate

Four pure functions; floats in, floats out; no rounding inside.

| Function | Rule | Raises `ValueError` when |
|---|---|---|
| `monthly_payment(principal, annual_rate, term_months)` | standard amortizing payment, `P·r / (1 − (1+r)^−n)` with `r = annual_rate/12`; at `annual_rate == 0` it is `principal / term_months` | `principal <= 0` or `term_months <= 0` |
| `debt_to_income(monthly_debt, monthly_gross_income)` | `monthly_debt / monthly_gross_income`, as a fraction (0.46 is 46%) | `monthly_gross_income <= 0` |
| `post_loan_dti(existing_monthly_debt, new_payment, monthly_gross_income)` | `debt_to_income(existing + new_payment, income)`: the number policy §4 uses | (via `debt_to_income`) |
| `income_discrepancy(stated_annual, verified_monthly)` | `(stated − verified·12) / (verified·12)`; positive means overstated | `verified_monthly * 12 <= 0` |

Inputs SPEC doesn't list (a negative rate or debt) aren't checked.

Worked checks: `monthly_payment(20_000, 0.149, 48)` is about 555.60;
`income_discrepancy(120_000, 7_000)` is about 0.4286.

## `decision/engine.py`: the agent proposes, the engine decides (ADR-0002)

Two types and one class.

- `PolicyFinding(code, outcome, section, message)`: one breach, with the policy
  section it comes from.
- `EngineResult(recommendation, findings, overridden_by_policy)`: `findings` is the full
  list from `evaluate_policy`. Its `reason_codes` property is the findings' codes in
  order, without duplicates, or `[ReasonCode.MEETS_ALL_CRITERIA]` when there are no
  findings. Every decision cites at least one code, including a clean case the agent
  escalated.

`DecisionEngine(thresholds=DEFAULT_THRESHOLDS)` stores the thresholds as `self.t` and
has two methods.

**`evaluate_policy(case)`** reads `case.metrics` (a dict whose keys the given analyzers in
`workflow/services.py` set: `credit_score`, `delinquencies_last_24m`, `post_loan_dti`,
`income_discrepancy`, `loan_to_annual_income`, `employment_tenure_months`, …; a metric may
be missing) and `case.all_signals`, and returns one finding per rule that fires, in this order. `t` is
the thresholds object.

| Rule | Condition | Code | Outcome | Section |
|---|---|---|---|---|
| Signals | each signal with severity `review` or `decline` | the signal's own code | MANUAL_REVIEW | 9.1 |
| Credit score (if present) | `< t.min_credit_score_decline_below` | CREDIT_SCORE_BELOW_MIN | DECLINE | 3.1 |
| | else `< t.min_credit_score_eligible` | CREDIT_SCORE_REVIEW_BAND | MANUAL_REVIEW | 3.2 |
| Delinquencies, `delinquencies_last_24m` | `>= t.delinquencies_decline_at` | RECENT_DELINQUENCY | DECLINE | 6.2 |
| | else `>= t.delinquencies_review_at` | RECENT_DELINQUENCY | MANUAL_REVIEW | 6.1 |
| `post_loan_dti` | `> t.dti_decline_above` | DTI_ABOVE_MAX | DECLINE | 4.3 |
| | else `> t.dti_review_above` | DTI_ABOVE_REVIEW_THRESHOLD | MANUAL_REVIEW | 4.2 |
| `income_discrepancy` | `> t.income_mismatch_review_above` | INCOME_MISMATCH | MANUAL_REVIEW | 5.4 |
| Loan amount (`case.application.loan.amount`) | `> t.max_loan_amount` | LOAN_AMOUNT_ABOVE_LIMIT | DECLINE | 7.1 |
| `loan_to_annual_income` | `> t.max_loan_to_annual_income` | LOAN_AMOUNT_ABOVE_LIMIT | MANUAL_REVIEW | 7.2 |
| `employment_tenure_months` | `< t.min_tenure_months_self_employed` when `case.application.employment.employment_type == "self_employed"`, else `< t.min_tenure_months_salaried` (every other type, including `contract` and `part_time`) | EMPLOYMENT_TENURE_SHORT | MANUAL_REVIEW | 2.3 / 2.2 |

- **Missing metrics:** a missing metric fires no rule. The analyzers already raised a
  review signal for missing data, and it arrives through the signals rule. The loan
  amount rule reads the application itself, so it always runs.
- **Signals escalate, they never decline.** A signal of severity `decline` is still
  MANUAL_REVIEW on purpose: only the numeric rules below decline. The finding's message
  is the signal's own message.

  The given identity-mismatch signal quotes both names. That is a privacy bug, found and
  fixed in Lesson 7, so don't copy it into your own messages.
- **The 580–659 band is §3.2.** §3.3 only says what passes.
- **Both loan rules can fire together.** §7.1 (DECLINE) and §7.2 (MANUAL_REVIEW) are
  separate checks, not if/else; both use LOAN_AMOUNT_ABOVE_LIMIT.
- **Messages.** No test checks message text. These are the reference wording (no
  personal data; numbers formatted as shown):
  - §3.1: `"Credit score {score:.0f} is below {t.min_credit_score_decline_below}."`
  - §3.2: `"Credit score {score:.0f} is in the review band."`
  - §6.x: `"{delinq:.0f} delinquencies in the last 24 months."`
  - §4.3: `"Post-loan DTI {dti:.1%} exceeds {t.dti_decline_above:.0%}."`
  - §4.2: `"Post-loan DTI {dti:.1%} is above {t.dti_review_above:.0%}."`
  - §5.4: `"Stated income exceeds verified income by {gap:.0%}."`
  - §7.1: `"Requested {amount:,.0f} exceeds the product maximum."`
  - §7.2: `"Loan is {lti:.0%} of verified annual income."`
  - §2.x: `"{tenure:.0f} months in current employment; policy minimum is {minimum}."`

**`decide(case, proposal)`** reconciles the policy outcome with the agent's proposal:

1. The policy outcome is the strictest finding (APPROVE < MANUAL_REVIEW < DECLINE), or
   APPROVE when there are no findings.
2. If the agent's recommendation is as strict as policy or stricter, it stands, with
   one exception: an agent DECLINE where policy does not decline becomes
   MANUAL_REVIEW. An agent may escalate; it may never decline on its own.
3. If the agent is less strict than policy, policy wins.
4. `overridden_by_policy` is true when the final recommendation differs from the
   agent's recommendation.

The tests and the samples to watch:
- APP-008: the rules stub approves at DTI 44%, and the engine overrides it to
  MANUAL_REVIEW.
- APP-005: a clear decline.

## Changes to earlier modules

None. This is the first lesson.

<!-- api:start -->

## Public API

### `src/underwriter/risk/calculations.py`

Imported elsewhere (keep these names exactly): `debt_to_income`, `income_discrepancy`, `monthly_payment`, `post_loan_dti`

- function `monthly_payment(principal: float, annual_rate: float, term_months: int) -> float`
  > Standard amortizing loan payment.
- function `debt_to_income(monthly_debt: float, monthly_gross_income: float) -> float`
  > DTI as a fraction (0.46 == 46%).
- function `post_loan_dti(existing_monthly_debt: float, new_payment: float, monthly_gross_income: float) -> float`
  > DTI after the requested loan is added. This is the number policy cares about.
- function `income_discrepancy(stated_annual: float, verified_monthly: float) -> float`
  > Relative gap between what the applicant said and what documents show.
  > Positive means the applicant overstated income.

### `src/underwriter/decision/engine.py`

Imported elsewhere (keep these names exactly): `DecisionEngine`

Builds on: `underwriter.decision.policy`, `underwriter.domain.models`

- class `PolicyFinding(BaseModel)`
  - field `code: ReasonCode`
  - field `outcome: Recommendation`
  - field `section: str`
  - field `message: str`
- class `EngineResult(BaseModel)`
  - field `recommendation: Recommendation`
  - field `findings: list[PolicyFinding]`
  - field `overridden_by_policy: bool`
  - method `@property reason_codes(self) -> list[ReasonCode]`
- class `DecisionEngine`
  - method `__init__(self, thresholds: PolicyThresholds=DEFAULT_THRESHOLDS) -> None`
  - method `evaluate_policy(self, case: UnderwritingCase) -> list[PolicyFinding]`
  - method `decide(self, case: UnderwritingCase, proposal: AgentRecommendation) -> EngineResult`

<!-- api:end -->
