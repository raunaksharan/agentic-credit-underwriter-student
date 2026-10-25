# Lesson 7 spec: traces, GenAI attributes and usage metering

**You build:**
- `src/underwriter/observability/tracing.py`
- `src/underwriter/observability/metering.py`
- `src/underwriter/observability/report.py`
- `src/underwriter/llm/instrumented.py`

**Given (the seed):** the Lesson 6 reference code, already instrumented. The workflow
graph, the orchestrator, the checks, the retriever and the agent's tool box call
`span`, `set_attrs`, `mark_error`, `redact` and `current_meter`. `run_node` copies the
context into worker threads. `UnderwritingDecision.usage` and the `trace` CLI command
exist. The two privacy fixes from the guide are in `services.py` and `checks.py`.

**Answer key:** `tests/test_observability.py`, the whole suite, `run-all` (8/8) and
`eval`.

```bash
uv run pytest tests/test_observability.py -k "cost or meter"    # metering
uv run pytest tests/test_observability.py                       # everything
uv run underwriter trace data/applications/APP-002.json         # read one trace
```

Every test imports `domain/models.py`, which imports `Usage` from `metering.py`. Until
`metering.py` exists, every test file errors at import, so build it first (or scaffold
first).

## `observability/metering.py`: what one decision cost

**`PRICES: dict[str, tuple[float, float]] = {"mock-underwriter-v1": (0.0, 0.0)}`** is in
USD per million tokens, as `(input, output)`. These are placeholders: a real price needs
the provider's own page and the date it was checked.

**Models** (pydantic):

- `ModelUsage`: `calls: int = 0`, `input_tokens: int = 0`, `output_tokens: int = 0`,
  `cost_usd: float = 0.0`.
- `Usage`:
  - `llm_calls: int = 0`, `input_tokens: int = 0`, `output_tokens: int = 0`;
  - `cost_usd: float = 0.0`;
  - `cost_known: bool = Field(True, description="False if a model had no price")`;
  - `by_model: dict[str, ModelUsage] = {}`;
  - `step_ms: dict[str, float] = Field({}, description="wall-clock time per workflow step")`;
  - `total_ms: float = 0.0`.

**`price_for(model) -> tuple[float, float] | None`:**
- `PRICES[model]` if listed;
- else `(float(LLM_PRICE_IN), float(LLM_PRICE_OUT))` when **both** environment variables
  are set and non-empty;
- else `None`.

**`UsageMeter()`** has a `usage: Usage` and per-step totals.

- `record_llm(model, input_tokens, output_tokens) -> float | None` updates
  `by_model[model]` (created on first use) and the totals: calls +1, and the tokens.
  - With a price, `cost = (input_tokens × in + output_tokens × out) / 1_000_000` is added
    to both, and returned.
  - With no price, `cost_known` becomes False, no cost is added, and it returns `None`.
    `cost_known` never goes back to True.
- `record_step(step, ms)` adds `ms` to that step's total, then sets
  `usage.step_ms = {step: round(total, 1)}` for every step.

**The current meter** lives in a `contextvars.ContextVar` named `"usage_meter"`, with
default `None`, so concurrent decisions never mix numbers.
- `current_meter() -> UsageMeter | None` reads it.
- `metering()` is a context manager. It sets a new `UsageMeter`, yields it, and resets
  the variable on exit (in `finally`), so a meter never outlives its decision.

## `observability/tracing.py`: spans, and no personal data in them

- `SERVICE_NAME = "agentic-credit-underwriter"`.
- **`setup_tracing(exporter=None) -> InMemorySpanExporter | None`** installs one
  `TracerProvider` (resource `service.name = SERVICE_NAME`) the first time, and does
  nothing after that. The kind is `exporter`, or `OTEL_EXPORTER`, or `"none"`, in
  lowercase:

  | Kind | Effect |
  |---|---|
  | `none` | no exporter |
  | `console` | `ConsoleSpanExporter` |
  | `memory` | an `InMemorySpanExporter`, kept and returned |
  | `otlp` | `BatchSpanProcessor(OTLPSpanExporter())`, imported inside the branch (optional extra) |
  | anything else | `ValueError(f"OTEL_EXPORTER must be none, console, memory or otlp, not {kind!r}")` |

  Console and memory exporters go through a `SimpleSpanProcessor`. Then call
  `trace.set_tracer_provider`, and return the in-memory exporter (or `None`). The kind is
  checked before the provider is stored, so a bad value raises on every call until it's
  fixed; that's intended.
- **`memory_exporter() -> InMemorySpanExporter`** calls `setup_tracing()`, then adds one
  in-memory exporter to the active provider if there isn't one yet, and returns it. Tests
  and the `trace` command use it.
- **`tracer()`** calls `setup_tracing()`, then returns `trace.get_tracer("underwriter")`.
- **`span(name, **attributes)`** is a context manager:
  1. Call `tracer().start_as_current_span(name, record_exception=False, set_status_on_exception=False)`.
  2. Call `set_attrs(s, **attributes)`, then yield the span.
  3. On an `Exception` inside the block: `mark_error(s, f"{type(exc).__name__}: {exc}")`,
     set `error.type` to the exception's class name, and re-raise.

  OpenTelemetry's own exception recording stays off, because it stores the raw message
  and a stack trace, and those can carry personal data.
- **`set_attrs(s, **attributes)`:**
  - skips `None` values;
  - turns lists and tuples into lists of `str`;
  - turns any value that isn't `str`, `bool`, `int` or `float` into `str(value)`;
  - sets the attribute with `__` replaced by `.` in the key (`gen_ai__usage__input_tokens`
    becomes `gen_ai.usage.input_tokens`).
- **`redact(text) -> str | None`** returns `None` for `None`. Otherwise it masks:
  - every email address (regex `[\w.+-]+@[\w-]+\.[\w.]+`) as `<email>`;
  - every run of 4 or more digits (`\d{4,}`) as `<digits>`.

  **Emails are masked first.** Masked the other way round, `jane1234@x.com` becomes
  `jane<digits>@x.com`, which no longer matches the email pattern, so the domain leaks.
- **`mark_error(s, description)`** sets
  `Status(StatusCode.ERROR, redact(description) or "")`.

## `llm/instrumented.py`: `InstrumentedLLM(inner, system="unknown")`

It is itself an `LLMClient`, so nothing else changes. It has `inner`, `system`, and
`model = inner.model`.

**`complete(messages, *, max_output_tokens=800, json_mode=False)`:**

1. Opens `span(f"chat {model}")` with these attributes:
   - `gen_ai.operation.name="chat"`, `gen_ai.system=system`;
   - `gen_ai.request.model=model`, `gen_ai.request.max_tokens=max_output_tokens`;
   - `llm.messages=len(messages)`.
2. Calls `inner.complete(messages, max_output_tokens=…, json_mode=…)`.
   - On `LLMUnavailable`: `mark_error(s, f"LLMUnavailable: {exc}")`, set
     `error.type="LLMUnavailable"`, and re-raise.
3. If `current_meter()` exists: `cost = meter.record_llm(resp.model, resp.input_tokens, resp.output_tokens)`.
4. Sets these attributes, then returns the response unchanged:
   - `gen_ai.response.model`;
   - `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`;
   - `llm.latency_ms=resp.latency_ms`;
   - `llm.cost_usd=cost` (dropped when `None`).

**Never record prompts or replies:** they hold case data. `__getattr__` forwards any
other attribute to `inner` (the mock's fault tooling reaches through).

## `observability/report.py`: `render_tree(spans) -> str`

**Constants:**
- `SHOWN`, the attributes worth seeing, in this display order:
  - `node.outcome`, `node.attempts`;
  - `check.status`, `check.required`, `check.reason`;
  - `retrieval.results`, `retrieval.abstained`;
  - `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`;
  - `tool.outcome`;
  - `decision.recommendation`, `decision.reason_codes`;
  - `llm.cost_usd`.
- `SHORT = {"gen_ai.usage.input_tokens": "in", "gen_ai.usage.output_tokens": "out", "decision.recommendation": "decision", "decision.reason_codes": "reasons"}`.

**Behaviour:**

- Group the spans by parent span id (`None` for roots), and sort each group by
  `start_time`.
- Write one line per span, depth first, roots first:
  - `prefix + branch + name`, padded to width `max(1, 40 - len(prefix) - len(branch))`;
  - then a space and the duration as `f"{ms:7.1f} ms"` (`(end_time - start_time) / 1e6`);
  - then two spaces and the shown attributes as `key=value`, joined by spaces. The key is
    `SHORT.get(attr, attr.split('.')[-1])`; tuple values are joined with `,`;
  - then `"  ✗"` if the span's status is ERROR.
- The branch is `""` for a root, `"└─ "` for the last child and `"├─ "` otherwise. A
  child's prefix grows by `""` under a root, by `"   "` under a last child, and by `"│  "`
  otherwise.
- Return the lines joined by newlines.

## Changes to earlier modules

None of yours. The instrumentation calls in earlier modules are part of the seed.

<!-- api:start -->

## Public API

### `src/underwriter/observability/metering.py`

Imported elsewhere (keep these names exactly): `Usage`, `UsageMeter`, `current_meter`, `metering`

- constant `PRICES = {'mock-underwriter-v1': (0.0, 0.0)}`
- class `ModelUsage(BaseModel)`
  - field `calls: int = 0`
  - field `input_tokens: int = 0`
  - field `output_tokens: int = 0`
  - field `cost_usd: float = 0.0`
- class `Usage(BaseModel)`
  > What one decision cost. Travels with the decision.
  - field `llm_calls: int = 0`
  - field `input_tokens: int = 0`
  - field `output_tokens: int = 0`
  - field `cost_usd: float = 0.0`
  - field `cost_known: bool = Field(True, description='False if a model had no price')`
  - field `by_model: dict[str, ModelUsage] = {}`
  - field `step_ms: dict[str, float] = Field({}, description='wall-clock time per workflow step')`
  - field `total_ms: float = 0.0`
- function `price_for(model: str) -> tuple[float, float] | None`
- class `UsageMeter`
  - method `__init__(self) -> None`
  - method `record_llm(self, model: str, input_tokens: int, output_tokens: int) -> float | None`
  - method `record_step(self, step: str, ms: float) -> None`
- function `current_meter() -> UsageMeter | None`
- function `metering()`

### `src/underwriter/observability/tracing.py`

Imported elsewhere (keep these names exactly): `mark_error`, `memory_exporter`, `redact`, `set_attrs`, `span`

- constant `SERVICE_NAME = 'agentic-credit-underwriter'`
- function `setup_tracing(exporter: str | None=None) -> InMemorySpanExporter | None`
  > Install the tracer provider once. Returns the in-memory exporter if used.
- function `memory_exporter() -> InMemorySpanExporter`
  > An in-memory exporter on the active provider, added once (tests, `trace`).
- function `tracer() -> trace.Tracer`
- function `span(name: str, **attributes) -> Iterator[Span]`
  > A span with attributes; None values are dropped. Exceptions mark it as an error.
- function `set_attrs(s: Span, **attributes) -> None`
- function `redact(text: str | None) -> str | None`
  > Safety net for free-text attributes (error messages): mask long digit runs and
  > emails. The real fix is never to put personal data in a message; this catches
  > the ones we miss.
- function `mark_error(s: Span, description: str) -> None`

### `src/underwriter/llm/instrumented.py`

Imported elsewhere (keep these names exactly): `InstrumentedLLM`

Builds on: `underwriter.llm.client`, `underwriter.observability.metering`, `underwriter.observability.tracing`

- class `InstrumentedLLM`
  - method `__init__(self, inner: LLMClient, system: str='unknown') -> None`
  - method `complete(self, messages: list[Message], *, max_output_tokens: int=800, json_mode: bool=False) -> LLMResponse`

### `src/underwriter/observability/report.py`

Imported elsewhere (keep these names exactly): `render_tree`

- constant `SHOWN = ('node.outcome', 'node.attempts', 'check.status', 'check.required', 'check.reason', 're…`
- constant `SHORT = {'gen_ai.usage.input_tokens': 'in', 'gen_ai.usage.output_tokens': 'out', 'decision.reco…`
- function `render_tree(spans: Sequence[ReadableSpan]) -> str`

<!-- api:end -->
