"""The eval harness: golden cases, failure injection, invariants, metrics, gates (lesson 6).

    uv run underwriter eval                       # all cases, gates, compare to baseline
    uv run underwriter eval --tag tools           # one family
    uv run underwriter eval --update-baseline     # accept the current numbers

Three layers of checks, from specific to general:

1. **Expectations** per case (evals/golden_cases.json): the decision, reason codes,
   agent validity, tool calls, overrides, audit steps.
2. **Invariants** on every case, whatever it expects. These are the properties a
   credit system must never violate (no unsafe approvals, no unfair declines, …).
3. **Gates** on the whole run (evals/gates.json): pass rate, safety counts, latency
   and token budgets, and regression against evals/baseline.json.

A unit test asks "does this function work?". An eval asks "is the system still
behaving the way the business signed off on?", including when things break.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/06-evaluation/SPEC.md; the tests are the answer key.
"""
