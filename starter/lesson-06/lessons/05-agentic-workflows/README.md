# Lesson 5 — Agentic Workflows: a graph that knows what to do when a step fails

> A script runs steps. A workflow knows, for every step, how long to wait, whether to
> try again, and who takes over when it can't finish.

**Slides:** [PDF](slides/lesson-05-agentic-workflows.pdf)
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-05/` in the course repo

## Objectives

By the end of this lesson students can:

1. Express a business workflow as a LangGraph graph with one typed state and an append-only audit.
2. Give every node its own timeout, retry count and failure mode (escalate, degrade, fallback).
3. Retry only transient failures, and explain why retrying a bug is harmful.
4. Route failures and MANUAL_REVIEW decisions to a human-review node.
5. Pause a run with `interrupt()`, checkpoint it, and resume it with a validated reviewer decision.

## What changed since lesson 4

| | Lesson 4 | Lesson 5 |
|---|---|---|
| Control flow | `run()` calls steps in order | LangGraph `StateGraph` (`workflow/graph.py`) |
| State | local variables | `UnderwritingState` (TypedDict); `audit` uses an append reducer |
| A step crashes | exception, request lost | per-node `NodePolicy`; required steps → `WORKFLOW_ERROR` → human |
| A step hangs | waits forever | per-node timeout |
| Human review | case put on a queue | `human_review` node; interactive runs pause with `interrupt()` |
| Reviewer decision | not modelled | `HumanReview(reviewer, decision, note)`; `final_recommendation` |
| New commands | — | `underwriter graph`, `run --node-fault`, `run --review-as` |

Every lesson 1–4 test passes unchanged: `UnderwritingWorkflow.run()` keeps its signature, and the nodes call the same components.

## Agenda

| Time | Block |
|---|---|
| 0:00 | From a script to a graph: nodes, edges, typed state (`underwriter graph`) |
| 0:15 | Reducers: why the audit is appended and never replaced |
| 0:30 | Node policies: timeout, retry, escalate / degrade / fallback (`workflow/resilience.py`) |
| 0:50 | The human-review edge: `interrupt()`, checkpoints, `Command(resume=…)` |
| 1:10 | What a checkpoint is allowed to deserialize, and why |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: which steps are required, and who decided? |

## Setup

```bash
cd solution/lesson-05          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run pytest            # 148 tests
uv run underwriter graph # paste into mermaid.live to see the diagram
```

## Walkthrough

```bash
uv run underwriter graph
uv run underwriter run data/applications/APP-001.json --node-fault income=transient  # retried
uv run underwriter run data/applications/APP-001.json --node-fault income=error      # escalated
uv run underwriter run data/applications/APP-001.json --node-fault analyze=hang      # timed out
uv run underwriter run data/applications/APP-001.json --node-fault policy=error      # degraded
uv run underwriter run data/applications/APP-005.json --node-fault agent=error       # still DECLINE
uv run underwriter run data/applications/APP-002.json \
    --review-as APPROVE --reviewer u-1042 --note "Payroll deposits confirm income."
```

Things to point at:

1. **The diagram.** Solid edges always run; dotted edges are decisions. `policy → escalate` doesn't exist: policy retrieval degrades by design.
2. **The audit reducer.** `audit: Annotated[list[AuditEvent], operator.add]`. A node returns only its new events. No node can rewrite history.
3. **`node_retry`** shows up in the trace with the error from attempt 1. Retries you can't see are retries you can't tune.
4. **Bugs aren't retried.** `income=error` raises a `RuntimeError` and fails on attempt 1. Only timeouts and `TransientNodeError` get another try.
5. **Degrade, logged.** With retrieval down, APP-001 still approves (the engine's thresholds never depended on RAG, F8), but the trace says `node_failure … degrade` and the decision has no citations. Is that acceptable for your client? That's exercise 2.
6. **The pause.** `--review-as` runs with `interactive=True`. The graph stops inside `human_review`, the checkpoint holds the state, and `resume()` continues the same thread with a `HumanReview`. The engine's MANUAL_REVIEW stays on the record; `final_recommendation` is the human's.
7. **Checkpoint allow-list.** Resuming deserializes saved state. `_serde()` allows exactly our domain types; anything else is refused.

## Lab exercises

### Exercise 1: A durable checkpointer (35 min)

Paused reviews live in memory, so they die with the process. Install `langgraph-checkpoint-sqlite`, pass a `SqliteSaver` into `build_graph(checkpointer=…)`, and add `underwriter resume <thread-id> --review-as …` that resumes a review started by a different process. Test it with two separate `UnderwritingWorkflow` instances.

### Exercise 2: Required or degrade? (30 min)

Your compliance lead says an approval without a policy citation is not acceptable. Change the policy node so that a degraded retrieval sends the case to review instead (keep the info signal). Write the test first. Then argue the opposite case in two sentences: when would degrading be the right call?

### Exercise 3: A reviewer SLA (35 min)

Add `assigned_to` and `due_by` to the request the graph sends at the pause, computed from the reason codes (identity cases: 4 hours; affordability: 1 business day). Put the numbers in one table in code, not in the node.

## Homework / deliverable

PR containing:

- [ ] SQLite checkpointer and a cross-process resume test
- [ ] The policy-node change with its test and your two-sentence counter-argument
- [ ] Reviewer SLA in the interrupt payload, with a test per reason family

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| State | One typed state; audit appended by a reducer | Globals or dicts passed around |
| Node policy | Timeout, retry and failure mode per node, written down | One try/except around everything |
| Retries | Transient errors only, visible in the audit | Retries everything, silently |
| Human review | Pause, checkpoint, validated resume, recorded reviewer | Email the case and hope |
| Safety | Checkpoints deserialize an allow-list of types | Deserialize anything |

## Interview questions this lesson prepares for

- Why use a graph framework instead of a function that calls steps in order?
- Which failures should you retry, and how do you avoid retrying bugs?
- How does human-in-the-loop work when the reviewer answers hours later?
- What does a checkpoint contain, and what are the security risks of loading one?
- One step is down. How do you decide between failing, degrading and falling back?

