# Lesson 4 — Tool-Using Agents: tools that fail, and an agent with limits

> A tool call is a network call. It will time out, rate-limit and return garbage.
> Give the agent tools it can't misuse, and a loop it can't run forever.

**Slides:** [PDF](slides/lesson-04-tool-agents.pdf)
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-04/` in the course repo

## Objectives

By the end of this lesson students can:

1. Wrap every external check so it returns a typed result (`OK`, `UNAVAILABLE`, `INVALID`) and never `None` or an exception.
2. Inject faults on demand (timeout, 429, 500, malformed payload, latency) and refuse to do so in production.
3. Separate required checks from optional ones, and say what each failure does to the decision.
4. Give an agent an allow-list of tools with validated arguments, and send refusals back to the model as tool results.
5. Bound the agent loop with a step cap and a deadline, and fall back to a human with a machine-readable reason.

## What changed since lesson 3

| | Lesson 3 | Lesson 4 |
|---|---|---|
| External systems | Bureau called directly; exception → `None` | Four checks behind `run_check`, each a typed `CheckResult` |
| Failure rehearsal | `--llm-fault` | plus `--tool-fault credit_bureau=timeout` / `TOOL_FAULTS=…` |
| Required vs optional | not modelled | credit + fraud required; bank + employment optional |
| Agent | one call + one repair | bounded loop: `check_policy`, `request_missing_document`, `get_check_result` |
| Limits | attempts | allow-list, 4 tool calls, deadline, one repair |
| New reason codes | — | `CHECK_UNAVAILABLE`, `AGENT_LIMIT_REACHED` |

`AGENT_MODE=single` (or `--agent single`) still runs the lesson 3 agent, so students can compare the two on the same case.

## Agenda

| Time | Block |
|---|---|
| 0:00 | Tools fail: the four ways, and why `None` is the worst answer (`tools/checks.py`) |
| 0:15 | Fault injection as a first-class feature (`tools/faults.py`) |
| 0:30 | Required vs optional checks, and what each failure does to the decision |
| 0:45 | The agent loop: allow-list, argument validation, refusals as results (`agents/tools.py`) |
| 1:00 | Limits: step cap, deadline, one repair, fallback (`agents/tool_agent.py`) |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: which limits would you tune first in production? |

## Setup

```bash
cd solution/lesson-04          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run pytest            # 130 tests
uv run underwriter run-all
```

## Walkthrough

```bash
# typed checks and fault injection
uv run underwriter run data/applications/APP-001.json                                   # APPROVE
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=timeout   # review
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=malformed # review
uv run underwriter run data/applications/APP-001.json --tool-fault fraud_screen=server_error
uv run underwriter run data/applications/APP-001.json --tool-fault bank_data=server_error  # APPROVE
uv run underwriter run data/applications/APP-005.json --tool-fault fraud_screen=timeout    # DECLINE

# the bounded agent
uv run underwriter run data/applications/APP-002.json                          # check_policy, cited
uv run underwriter run data/applications/APP-007.json                          # requests tax_return
uv run underwriter run data/applications/APP-001.json --llm-fault loop          # cut off at 4 calls
uv run underwriter run data/applications/APP-001.json --llm-fault disallowed_tool  # refused, recovers
uv run underwriter run data/applications/APP-005.json --llm-fault loop          # still DECLINE
```

Things to point at:

1. **The trace** shows each check with its status and reason: `UNAVAILABLE: credit_bureau: timed out`. Nobody has to guess why the case went to a human.
2. **Malformed is not OK.** The bureau "answered", but the payload failed validation, so it is `INVALID`. A score of `"seven hundred"` must never reach the engine.
3. **Optional means optional.** A bank-data outage costs us corroboration, not the decision. Write down which checks are required, and why, before you build them.
4. **`approve_loan` doesn't exist.** The model asked for it; the allow-list said no, the refusal went back as a tool result, and the agent carried on. The tools can read and request; none of them can decide.
5. **The loop is bounded three ways**: tool calls, wall-clock deadline, repairs. Each limit has its own message in `validation_errors`, and all of them end in `AGENT_LIMIT_REACHED` or `INVALID_MODEL_OUTPUT` → manual review.
6. **Policy still wins.** APP-005 declines whether the agent loops, fails or behaves.

## Lab exercises

### Exercise 1: A new fault kind (30 min)

Add `slow_then_ok` to `FaultPlan`: the first call sleeps past a timeout, later calls succeed. Write the test first. You will need it again in lesson 8, when retries arrive.

### Exercise 2: A new tool (40 min)

Add `get_metric(name)` to the agent's tool box: it returns one metric with its id, or an error listing the available names. Validate the argument with a pydantic model, add it to the allow-list, and test that an unknown name comes back as an error result, not an exception.

### Exercise 3: Tune the limits (30 min)

Run the suite with `MAX_TOOL_CALLS` at 1, 2 and 4. Which samples change, and why? Then set `AGENT_DEADLINE_S=0.001` and explain the result. Write down the limits you would ship with and one sentence on each.

## Homework / deliverable

PR containing:

- [ ] `slow_then_ok` with its test
- [ ] `get_metric` tool, allow-listed and tested
- [ ] A short note: your chosen limits, and the failure each one prevents

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Tool results | Typed status with a reason, never `None` | Exceptions or silent defaults |
| Faults | Reproducible on demand; refused in production | "It failed once in staging" |
| Required vs optional | Written down; each failure has a defined effect | Every failure treated the same |
| Allow-list | Unknown tools and bad arguments refused as results | Model output executed directly |
| Limits | Step cap, deadline, one repair, typed fallback | `while True` until it works |

## Interview questions this lesson prepares for

- A tool your agent depends on is down. What happens to the request?
- How do you stop an agent from looping or running up cost?
- How do you stop an agent from calling a tool it shouldn't?
- How do you test failures you can't reproduce on demand?
- Which external checks are required for a decision, and how did you decide?

