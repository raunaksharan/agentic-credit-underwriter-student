---
name: add-policy-rule
description: Add a new lending-policy rule end to end (reason code, threshold, metric, engine finding, tests, sample case). Use when a request says "policy says…", adds an eligibility limit, or changes when the engine declines or escalates.
---

# Add a policy rule

A policy rule is a business commitment. The engine enforces it; the LLM never does.
Work in this order and stop at step 1 if the rule is ambiguous.

1. **Pin the rule in words.** Quote the policy section (`data/policies/…` or the
   request). Write the threshold, the comparison (`>` or `>=`), the unit, and the
   outcome: DECLINE, MANUAL_REVIEW, or info only. If any of these is unclear, ask.
2. **Reason code.** Add one `ReasonCode` in `domain/models.py`, named for the fact
   (`APPLICANT_UNDER_MIN_AGE`), not the outcome.
3. **Threshold.** Add a field to `PolicyThresholds` in `decision/policy.py` with a
   comment naming the policy section. No magic numbers anywhere else.
4. **Metric.** Compute the input in the analyzer that owns that data
   (`workflow/services.py`), as an exact calculation in `risk/calculations.py` if it's
   arithmetic. Missing input → a review signal, never a default value.
5. **Engine finding.** In `DecisionEngine.evaluate_policy`, add one `PolicyFinding`
   citing the section. DECLINE only for a clear breach; anything uncertain is
   MANUAL_REVIEW.
6. **Tests first, both sides.** In `tests/test_decision_engine.py`: just inside the
   threshold, exactly on it, just outside it, and the input missing.
7. **Sample case.** If the rule needs a worked example, add `APP-0NN` to
   `data/applications/` and `data/expected_outcomes.json`, with the expected outcome
   taken from the policy text.
8. **Document.** One row in `architecture/failure-modes.md` if the rule handles a
   failure; one line in the lesson guide if a student will meet it.
9. **Verify.** Run `/verify`. `run-all` must stay at N/N.

Never: let the agent's proposal or retrieved text change the threshold; decline on
missing data; edit an existing test to make the new rule pass.
