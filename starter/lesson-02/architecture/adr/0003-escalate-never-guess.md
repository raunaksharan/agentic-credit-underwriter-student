# ADR-0003: Missing or conflicting data escalates; nothing is guessed

**Status:** Accepted · Lesson 1

## Context

LLMs fill gaps fluently. In lending, a filled gap (an assumed credit score, income
taken from the application form instead of a document) is a compliance failure
that looks like a normal decision.

## Decision

1. Unavailable data is represented explicitly: `None` plus a `ReasonCode`
   (`CREDIT_DATA_UNAVAILABLE`, `MISSING_DOCUMENT`, `INCOME_UNVERIFIED`).
2. Downstream calculations that depend on missing data are **not** computed
   (no DTI without verified income).
3. Any such signal routes the case to human review, with the missing items listed.
4. Tools raise typed exceptions (`CreditDataUnavailable`); they never return defaults.

## Consequences

- Some cases that a person could resolve in a minute go to the queue. That cost is
  visible and measurable; silent guessing is neither.
- Tests assert absence: `credit_score` must not appear in APP-003's metrics.
