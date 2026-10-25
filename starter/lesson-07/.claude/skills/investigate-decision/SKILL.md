---
name: investigate-decision
description: Explain why the system decided what it did for one application (approve, decline or escalate), from the reason codes, audit trail, trace and cited policy. Use when someone asks "why was APP-00X declined/escalated?" or a decision looks wrong.
---

# Investigate a decision

The answer must come from what the system recorded, not from a plausible story.

1. **Run the case,** with the same faults if the question is about a failure:
   `uv run underwriter run data/applications/APP-00N.json [--llm-fault …] [--tool-fault …] [--node-fault …]`.
2. **Read in this order:**
   1. the recommendation and reason codes;
   2. what the agent proposed, and whether policy overrode it;
   3. the metrics (post-loan DTI, credit score, income discrepancy, …);
   4. the trail, step by step;
   5. for each engine finding with its policy section, add `--json` and read the
      `decision_engine` audit event's `findings`;
   6. the agent's proposal: valid, attempts, tool calls, citations;
   7. from lesson 7, `uv run underwriter trace data/applications/APP-00N.json`: which
      step took the time, failed or retried, and the token counts.
3. **Tie each reason code to its source:** the policy section in
   `data/policies/unsecured_personal_lending_policy.md` or the regulation cited, and the
   metric that crossed it (for example post-loan DTI 45.6% > 43%, policy §4.2).
4. **Answer in three parts:** the decision; the facts and rules that produced it (with
   sections); and what a human reviewer needs to look at, if it escalated.
5. **If it looks wrong,** compare with `data/expected_outcomes.json` or the golden case,
   and switch to `debug-root-cause`. Don't argue the system into a different answer.

<rules>
- Never put the applicant's name, ID digits, email or address in the explanation;
  refer to the application id.
- The model's rationale is evidence of what it proposed, not of why the case was
  decided. The engine's findings are the reason.
</rules>
