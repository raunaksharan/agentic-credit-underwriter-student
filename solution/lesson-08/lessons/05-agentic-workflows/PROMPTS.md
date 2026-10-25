# Lesson 5 prompt pack: build the workflow graph (take-home)

This lesson is written to be done on your own, in about two hours. Read the lesson
guide first; its walkthrough explains every behaviour the tests check. Then build the
two modules in `SPEC.md` with Claude Code.

```bash
cd ~/fde-work/lesson-05        # your copy of starter/lesson-05 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: resilience and the graph
claude
```

```text
/start-lesson 05
```

## 1. Clarify and plan (15 min)

```text
/plan-lesson 05
```

Then ask Claude to explain the graph in SPEC.md as you'd explain it to a risk officer:
which steps escalate, which degrade, which fall back, and why.

Then scaffold the interfaces (5 min). Test files import names from several of this
lesson's modules at the top, so until every name exists each file errors at import and
the per-step test commands below can't run. The scaffold makes each test fail on its own.
Skip it only if you'll write every module before running any test:

```text
<task>Scaffold the public API of lesson 05's modules</task>
<spec>lessons/05-agentic-workflows/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one (NotImplementedError) rather than at import, and
ruff is clean. No logic yet.</done_when>
```

## 2. Timeouts, retries and failure (30 min)

```text
<task>Build src/underwriter/workflow/resilience.py: TransientNodeError, NodeFailed,
NodePolicy, NodeRun, NodeFaults, run_node</task>
<spec>lessons/05-agentic-workflows/SPEC.md, section "workflow/resilience.py"</spec>
<tests>uv run pytest tests/test_workflow_graph.py -k "run_node or production"</tests>
<constraints>Only timeouts and TransientNodeError are retried. A bug fails on its first
attempt. Faults are refused when APP_ENV=production.</constraints>
<done_when>Those tests pass and ruff is clean.</done_when>
```

Ask Claude what happens to the thread of an attempt that timed out. SPEC.md answers it;
check the answer.

## 3. The graph (60 min)

```text
<task>Build src/underwriter/workflow/graph.py: NODE_POLICIES, UnderwritingState,
build_graph (guarded, the nodes, escalate, human_review, the edges) and _serde</task>
<spec>lessons/05-agentic-workflows/SPEC.md, section "workflow/graph.py"</spec>
<tests>uv run pytest tests/test_workflow_graph.py -q, then uv run pytest and uv run underwriter run-all</tests>
<constraints>Audit is append-only: a node returns only its new events, and guarded merges
lists, never replaces them. Nodes call the orchestrator's components; no business logic
inline. The checkpoint serializer allows only the domain types.</constraints>
<done_when>The whole suite is green, run-all shows 8/8, and uv run underwriter graph draws the designed shape.</done_when>
```

Build it in two passes if that's easier:
1. `guarded`, the seven nodes and the straight edges. These tests go green first:
   `-k "retried or degrades or never_pause or shape"`.
2. `escalate`, `human_review` and the conditional edges. Every escalated case ends in
   `human_review`, so the escalation tests need both.

```bash
uv run underwriter run data/applications/APP-001.json --node-fault income=transient  # retried
uv run underwriter run data/applications/APP-001.json --node-fault income=error      # escalated
uv run underwriter run data/applications/APP-001.json --node-fault policy=error      # degraded
uv run underwriter run data/applications/APP-002.json \
  --review-as APPROVE --reviewer uw-017 --note "income verified by phone"            # paused, resumed
```

## 4. Verify, review, learn (15 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest` and `run-all` are green.
- Your PR explains, in your own words, the difference between escalate, degrade and
  fallback, with one node of each from this graph.

## Don't delegate

Which nodes escalate and which degrade (`NODE_POLICIES`). It's the guide's exercise 2,
and it's a business decision.
