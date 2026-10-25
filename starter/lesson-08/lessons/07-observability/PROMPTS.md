# Lesson 7 prompt pack: build tracing, metering and the instrumented client with Claude Code

You build four modules from `SPEC.md`. The rest of the system already calls them:
- the graph, the checks, the retriever and the tool box open spans;
- the orchestrator opens a meter per decision;
- `run_node` carries the context into worker threads.

So the tests and the `trace` command work as soon as your modules do.

```bash
cd ~/fde-work/lesson-07        # your copy of starter/lesson-07 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: every file, until metering.py exists
claude
```

```text
/start-lesson 07
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 07
```

The order is metering, then tracing with the instrumented client, then the report.
Reject a plan that starts with tracing: `domain/models.py` imports `Usage`, so nothing
imports at all until `metering.py` exists.

Then scaffold the interfaces (5 min). The scaffold makes each test fail on its own
rather than at import:

```text
<task>Scaffold the public API of lesson 07's modules</task>
<spec>lessons/07-observability/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one rather than at import, and ruff is clean. No
logic yet.</done_when>
```

## 2. Metering (20 min)

```text
<task>Build src/underwriter/observability/metering.py: PRICES, ModelUsage, Usage,
price_for, UsageMeter, current_meter, metering</task>
<spec>lessons/07-observability/SPEC.md, section "observability/metering.py"</spec>
<tests>uv run pytest tests/test_observability.py -k "cost or meter"</tests>
<constraints>The meter lives in a ContextVar and is reset in `finally`. An unpriced model
sets cost_known False and adds no cost; never guess a price. PRICES values are
placeholders.</constraints>
<done_when>Those tests pass and ruff is clean.</done_when>
```

This command needs the scaffold. `tests/test_observability.py` imports `tracing` and
`report` at the top, so without the scaffold the file can't even be collected yet.

Ask Claude why the meter is a context variable and not a module global. What would two
decisions running at once see?

## 3. Tracing and the instrumented client (30 min)

```text
<task>Build src/underwriter/observability/tracing.py (setup_tracing, memory_exporter,
tracer, span, set_attrs, redact, mark_error) and src/underwriter/llm/instrumented.py
(InstrumentedLLM)</task>
<spec>lessons/07-observability/SPEC.md, sections "observability/tracing.py" and
"llm/instrumented.py"</spec>
<tests>uv run pytest -k "not trace_tree", then uv run underwriter run-all</tests>
<constraints>No personal data in any span: never record prompts or replies; pass free text
through `redact`; turn off OpenTelemetry's own exception recording (it stores raw messages). The provider is installed once. GenAI attribute names exactly
as SPEC.md gives them. The wrapper re-raises LLMUnavailable after marking the span.</constraints>
<done_when>All tests but the tree test pass, run-all shows 8/8, and ruff is clean.</done_when>
```

Then ask Claude what happens to the `check credit_bureau` span's parent if `run_node`
didn't copy the context into the worker thread. Find the line in
`workflow/resilience.py`.

## 4. The span tree (15 min)

```text
<task>Build src/underwriter/observability/report.py: SHOWN, SHORT, render_tree</task>
<spec>lessons/07-observability/SPEC.md, section "observability/report.py"</spec>
<tests>uv run pytest, then uv run underwriter trace data/applications/APP-002.json</tests>
<constraints>Children sorted by start time; the branch and prefix characters exactly as
SPEC.md gives them; errors flagged with ✗.</constraints>
<done_when>The whole suite is green, run-all shows 8/8, eval passes, and `trace` prints
one tree rooted at `underwrite APP-002`.</done_when>
```

Read a trace under faults:

```bash
uv run underwriter trace data/applications/APP-001.json --tool-fault bank_data=server_error
uv run underwriter trace data/applications/APP-001.json --node-fault income=transient
```

Where did the time go? Which span is red, and does the decision still stand?

## 5. Verify, review, learn (10 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest`, `run-all` (8/8) and `eval` are green.
- `trace` prints the tree, and you can say which step took the longest and why.
- Your PR answers: what is the difference between the audit trail and a trace, and why
  must neither carry personal data?

## Don't delegate

What counts as personal data, and the prices. A price needs the provider's own page and
the date you checked it.
