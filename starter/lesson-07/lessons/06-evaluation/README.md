# Lesson 6 — Testing & Evaluation: prove it still behaves, including when it breaks

> A unit test asks "does this function work?". An eval asks "is the system still
> behaving the way the business signed off on?", on the bad days too.

**Slides:** [PDF](slides/lesson-06-evaluation.pdf)
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-06/` in the course repo

## Objectives

By the end of this lesson students can:

1. Write golden cases that pin a decision, its reasons and its behaviour (tool calls, retries, overrides).
2. Combine golden cases with the fault injection from lessons 3–5, so failures are evaluated, not just happy paths.
3. State the invariants a credit system must never break, and check them on every case.
4. Turn a run into metrics (accuracy, safety, escalation, validity, cost, latency) and gate a release on them.
5. Show that the harness catches regressions by breaking the system on purpose.

## What changed since lesson 5

| | Lesson 5 | Lesson 6 |
|---|---|---|
| Sample check | `run-all`: 8 cases, decision only | `underwriter eval`: 32 cases in 5 families |
| Failures | rehearsed by hand with flags | each fault is a golden case |
| What is checked | the recommendation | decision, reasons, agent validity, tool calls, overrides, audit steps, citations |
| Safety | implied | invariants on every case: no unsafe approval, no unfair decline, … |
| Release decision | "tests are green" | gates in `evals/gates.json`, regression vs `evals/baseline.json` |

## The three layers

| Layer | Where | Example |
|---|---|---|
| Expectations, per case | `evals/golden_cases.json` | G-A01: loop → MANUAL_REVIEW, `AGENT_LIMIT_REACHED`, exactly 4 tool calls |
| Invariants, every case | `invariant_violations()` | never APPROVE a case that should not be approved |
| Gates, whole run | `evals/gates.json` | pass rate 100 %, 0 unsafe approvals, p95 ≤ 5 s, tokens ≤ +20 % vs baseline |

## Agenda

| Time | Block |
|---|---|
| 0:00 | Tests vs evals: what each one can and can't tell you |
| 0:15 | Golden cases: one case = one sentence of the business spec |
| 0:30 | Invariants: the rules that hold on every case |
| 0:45 | Metrics and gates; why cost and latency are gated too |
| 1:00 | Mutation drills: break it, watch the gates fail |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: which gate would you never relax? |

## Setup

```bash
cd solution/lesson-06          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run pytest              # 157 tests
uv run underwriter eval    # 32/32, all gates pass
```

## Walkthrough

```bash
uv run underwriter eval
uv run underwriter eval --tag tools
uv run underwriter eval --markdown /tmp/eval.md && cat /tmp/eval.md
```

Then break it, live (each in turn, revert after):

1. In `decision/policy.py` change `dti_review_above` from `0.43` to `0.47`. Run `underwriter eval`. G-B02 and G-B08 now approve, and the gates fail on **unsafe approvals** and **pass rate**.
2. In `ChecksAnalyzer.analyze`, drop the `CHECK_UNAVAILABLE` signal. G-T04 (fraud screen down) now approves: an unsafe approval.
3. Give the agent `max_tool_calls=40`. G-A01 fails (40 calls, not 4) and so does the **mean input tokens** gate. Cost is a release criterion.

Things to point at:

1. **Every failure family is a case**: LLM faults, agent faults, tool faults, node faults. A failure you rehearsed once by hand is a failure you will forget to check.
2. **Invariants don't care what the case expected.** They hold even for a case someone writes wrongly.
3. **Escalation rate is 62 %** because most cases are failure drills. On real traffic it is a business metric with a target. Ask the room what the target should be.
4. **Override rate** (engine overrode the agent): a quality signal for the model. If a new prompt raises it, the prompt got worse, even when every decision is still right.
5. **The drill that didn't mutate.** Patching `tool_agent.MAX_TOOL_CALLS` changes nothing, because the default argument was bound at import. The eval stays green and looks like a pass. That's why the harness has its own tests (`tests/test_eval_harness.py`), including one that breaks the policy and asserts the gates fail.

## Lab exercises

### Exercise 1: Five new golden cases (30 min)

Write five cases for situations the suite doesn't cover yet: for example a bureau `latency:300` fault, two faults at once, or the `single` agent with `wrong_number`. Each case needs a scenario sentence a credit officer would agree with. Run the suite, then `--update-baseline`, and explain the metric changes in your PR.

### Exercise 2: A new invariant (35 min)

Add: "a DECLINE always carries at least one policy reason code" (credit score, DTI, delinquency, loan limits). Write a test that forges a decision breaking it. Then find out whether any real case breaks it.

### Exercise 3: Mutation drill (35 min)

Pick a line in `decision/engine.py` or `workflow/services.py`, change it in a way that seems harmless, and run the eval. If nothing fails, write the golden case that would have caught it. Repeat once more.

## Homework / deliverable

PR containing:

- [ ] Five new golden cases with scenario sentences, and the updated baseline
- [ ] The DECLINE-needs-a-policy-reason invariant with its test
- [ ] Two mutation drills: the change, what the eval said, and the case you added

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Golden cases | One business sentence each; behaviour as well as outcome | "Output equals snapshot" |
| Failure coverage | Every fault family has cases | Happy paths only |
| Invariants | Checked on every case, independent of expectations | Folded into individual asserts |
| Gates | Safety, quality, cost and latency, in a file | "Tests pass" |
| Harness trust | Mutation drills prove it can fail | Has only ever been green |

## Interview questions this lesson prepares for

- How do you evaluate an LLM system when the output isn't deterministic?
- What is the difference between a test and an eval?
- Which metrics would block a release of a credit model, and why those?
- How do you know your eval would catch a regression?
- How do you keep eval cost and runtime under control?

