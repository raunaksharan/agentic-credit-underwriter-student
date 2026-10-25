# Lesson 7 — Observability: answer "why was this slow, what did it cost, what failed?"

> For any decision you must be able to answer four questions: why did it take this
> long, which tool failed, how many tokens did it use, and which model made the call?

**Slides:** [PDF](slides/lesson-07-observability.pdf)
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-07/` in the course repo

## Objectives

By the end of this lesson students can:

1. Instrument a workflow with OpenTelemetry: one root span per decision, child spans for every node, external check, retrieval, LLM call and agent tool call.
2. Record LLM calls with the GenAI semantic-convention attributes (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, …) and never record prompts or replies.
3. Propagate trace context into worker threads, and explain what breaks when you don't.
4. Meter every decision: LLM calls, tokens, cost from a price table, time per step.
5. Keep personal data out of prompts, messages and telemetry, and prove it with tests.
6. Read a trace to find where the time went, including time no step owns.

## What changed since lesson 6

| | Lesson 6 | Lesson 7 |
|---|---|---|
| Where did time go? | total latency per eval case | span per node, check, retrieval, LLM call, tool call |
| Tokens | on the agent's proposal | `gen_ai.usage.*` on each LLM span, summed into `decision.usage` |
| Cost | not known | `usage.cost_usd` from `PRICES` (placeholder prices; `cost_known` says if any model was unpriced) |
| Export | — | `OTEL_EXPORTER=none|console|memory|otlp`; `uv sync --extra otel` for OTLP |
| CLI | — | `underwriter trace <app>`; `run` prints a usage line |
| Personal data | lesson 3 context test on one sample | PII tests over all 8 samples, for the LLM context and for every span |
| Eval | — | LLM calls and cost per case; invariant: every decision has a usage record |

## Two findings from building this lesson

Instrumenting the system found two real privacy bugs that every earlier test missed:

1. **ID digits in a bureau error.** For APP-003, the credit check passed the bureau's own message ("no record for applicant ending 5562") into a signal. Signals reach the LLM context and now traces. Fixed at source: our message names no one.
2. **Names in the identity-mismatch signal.** For APP-006 the signal said "Payslip names 'James Whitmore', application names 'James Whitfield'", so both names went to the model. The message is now generic; the names moved to the evidence, which goes only to the audit trail.

The lesson 3 PII test checked one sample (APP-001), which had neither problem. It now checks all eight. This is the point of the lesson: telemetry is another place data goes, and looking at it closely shows you where data already went.

## Agenda

| Time | Block |
|---|---|
| 0:00 | Audit vs logs vs traces vs metrics: who reads each, how long it's kept |
| 0:15 | Spans, attributes, status; the span tree for one decision (`underwriter trace`) |
| 0:30 | GenAI conventions; what never goes in a span |
| 0:45 | Context propagation: the thread bug, and `copy_context().run` |
| 1:00 | Metering: tokens to dollars, `cost_known`, step times |
| 1:10 | The two privacy findings |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: what would you alert on? |

## Setup

```bash
cd solution/lesson-07          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run pytest            # 182 tests
uv run underwriter trace data/applications/APP-002.json
```

Optional, to see traces in a real UI:

```bash
uv sync --all-groups --extra otel
docker run --rm -d -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one
OTEL_EXPORTER=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
  uv run underwriter run-all
# open http://localhost:16686 and pick the service agentic-credit-underwriter
```

Check the Jaeger docs for the current image name and ports before class.

## Walkthrough

```bash
uv run underwriter trace data/applications/APP-002.json
uv run underwriter trace data/applications/APP-001.json --tool-fault bank_data=server_error
uv run underwriter trace data/applications/APP-001.json --node-fault income=transient
uv run underwriter trace data/applications/APP-001.json --llm-fault loop
uv run underwriter run data/applications/APP-002.json        # the Usage: line
```

Things to point at:

1. **One tree per decision.** `underwrite APP-002` → nodes → checks, retrievals, chat calls, agent tools. Every span has a parent; that only works because `run_node` copies the context into its worker thread.
2. **✗ marks a failed span.** The bank outage is an error span under `node checks`, while the decision still approves. Errors in telemetry aren't the same as errors in the decision.
3. **Retries are attributes:** `attempts=2 outcome=retried` on `node income`.
4. **Tokens per call.** The looping agent shows five chat spans and four tool spans, and the cost of a loop is visible before anyone reads the code.
5. **Time nobody owns.** About 20 ms total and 11–15 ms in nodes: the rest is the graph engine checkpointing state between steps. The first run in a process takes ~0.4 s of one-time warm-up, which is why `trace` runs the case twice.
6. **Look at the retrievals.** The agent's `check_policy` retrieval takes several times longer than the analyzer's. Why? (Exercise 1.)

## Lab exercises

### Exercise 1: Explain the slow span (30 min)

The `retrieve` span under `tool check_policy` is several times slower than the three under `node policy`. Find out why, using spans only (add attributes if you need them, such as query length or candidate count). Write the cause in two sentences, and either fix it or say why it doesn't matter.

### Exercise 2: Metrics (40 min)

Traces are per decision. Add OpenTelemetry *metrics* for the fleet view: a counter `underwriter.decisions` by recommendation, a histogram `underwriter.decision.duration`, and a counter `gen_ai.client.token.usage` by model and token type. Test them with an in-memory metric reader.

### Exercise 3: A real price (30 min)

Pick the model you'd use in production. Look up its current per-token price on the provider's own pricing page, add it to `PRICES` with the date you checked, and run `run-all` with `LLM_MODE=live` (or compute from the mock's token counts). What does one decision cost? What does a looping agent cost?

## Homework / deliverable

PR containing:

- [ ] The slow-span explanation (and fix, if any)
- [ ] The three metrics with tests
- [ ] A price entry with its source and date, and a cost-per-decision note

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Coverage | Every node, tool, retrieval and model call is a span | Only the top level |
| Attributes | Conventions used; outcome, attempts, tokens, status | Free-text blobs |
| Context | Correct parents across threads, tested | Orphan spans |
| Privacy | No PII in spans or prompts, tested on every sample | "We don't log names" |
| Cost | Per decision, with unknown prices flagged | A monthly bill surprise |

## Interview questions this lesson prepares for

- What would you put on an LLM span, and what would you never put there?
- How do you find out why one request was slow in a multi-step agent?
- How do you attribute token cost to a customer, a decision or a feature?
- What's the difference between the audit trail and the traces, and who reads each?
- Your spans have no parent in production. What happened?

