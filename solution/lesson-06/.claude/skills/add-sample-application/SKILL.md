---
name: add-sample-application
description: Add a synthetic loan application (applicant, documents, bureau record) with its expected outcome taken from the policy. Use when a scenario needs a new worked example, a new edge case, or a rule needs a sample to exercise it.
---

# Add a sample application

Every sample exists to exercise one path through the system, and its expected outcome
comes from reading the policy, never from running the system.

1. **Write the scenario sentence** the way a credit officer would: "Salaried applicant
   with 4 months' tenure and otherwise strong file." Ask if the path it should exercise
   isn't clear (`clarify-before-building`).
2. **Derive the expected outcome by reading** `data/policies/unsecured_personal_lending_policy.md`
   and `decision/policy.py`: the section, the threshold, the comparison, and the outcome.
   Write the arithmetic out (payment, post-loan DTI, loan-to-income) and check it with
   `risk/calculations.py`, not by hand-waving.
3. **Add the case** to `CASES` in `scripts/generate_sample_data.py`: next id `APP-0NN`, a
   fictional person (an `example.com` email, made-up address and ID digits), employer,
   income, loan, debts, documents, a bureau record (or `None` for "no record"), and
   `expected`. Everything is fictional; never use a real person.
4. **Generate:** `uv run python scripts/generate_sample_data.py`. It writes
   `data/applications/`, `data/documents/APP-0NN/`, `data/bureau/credit_reports.json` and
   `data/expected_outcomes.json`.
5. **Run it:** `uv run underwriter run data/applications/APP-0NN.json`. If the result
   differs from the expectation, find out which one is wrong (`debug-root-cause`) and say
   so. Don't change the expectation to match the output.
6. **Tests and evals:**
   - `run-all` must now show N+1/N+1.
   - The data-contract tests read every file in `data/applications/`, so they cover it
     at once.
   - The PII tests in `tests/test_llm_agent.py` and `tests/test_observability.py` list
     APP-001…APP-008 by hand. Ask before extending them, since tests aren't yours to
     edit.
   - From lesson 6, add a golden case (`add-golden-case`).
7. **Verify:** `/verify`.

<rules>
- The sample's documents must agree with its application unless the disagreement is the
  scenario (as in APP-004 and APP-006).
- Names and ids never appear in messages; they live in the application and the evidence.
</rules>
