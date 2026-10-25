---
name: add-golden-case
description: Write a golden eval case for evals/golden_cases.json with an expectation taken from policy, not from system output. Use when adding eval coverage, a regression case, or a failure scenario to the eval suite.
---

# Add a golden case

A golden case is one sentence of the business spec, made executable. If the expected
answer comes from running the system, the case proves nothing.

1. **Write the scenario sentence first,** the way a credit officer would say it:
   "Required fraud screen returns 500 on a clean application."
2. **Derive the expectation by reading,** not by running: the policy section, the
   failure-modes table, or the lesson guide. Note the source in your reply.
3. **Pick the inputs:** an existing application in `data/applications/` and, if it's a
   failure drill, one of `llm_fault`, `tool_fault`, `node_fault`, `agent`.
4. **Choose the assertions** (`Expect` in `evaluation/harness.py`): the recommendation
   always; reason codes that must appear; and behaviour where it matters
   (`tool_calls`, `tools_called`, `tools_rejected`, `overridden`, `audit_include`,
   `citations_min`). Prefer a few precise assertions to many loose ones.
5. **Id and tags.** Next free id in the family (`G-T08`); tags from baseline, llm,
   agent, tools, workflow, plus `safety` if a policy decline must survive a failure.
6. **Run it:** `uv run underwriter eval --tag <family>`. If it fails, decide whether the
   case or the system is wrong, and say which. Never edit the case to match the output
   without a reason you can quote.
7. **Baseline.** When the suite passes, `uv run underwriter eval --update-baseline` and
   explain the metric changes in one line each.
