# Lesson 5 spec: a workflow graph with per-node failure policies (take-home)

**You build:** `src/underwriter/workflow/resilience.py` and `src/underwriter/workflow/graph.py`.

**Given (the seed):** the Lesson 4 reference code, plus:
- the orchestrator, which owns the components and calls
  `build_graph(self, node_faults, node_policies)`. It has these methods:
  - `run_checks`, `build_case`, `run_analyzers`;
  - `income_verifier`, `policy_analyzer`, `agent`, `engine`, `review_queue`;
  - `run`, `start`, `resume`.
- `HumanReview` and the `WORKFLOW_ERROR` reason code in `domain/models.py`;
- the CLI (`graph`, `--node-fault`, `--review-as`).

**Answer key:** `tests/test_workflow_graph.py`, the whole suite, and `run-all`.

```bash
uv run pytest tests/test_workflow_graph.py -k "run_node or production"   # resilience
uv run pytest                                                            # the graph
uv run underwriter graph                                                    # the diagram
```

## `workflow/resilience.py`: timeout, retry, and what failure means

- `NODE_FAULT_KINDS = {"error", "transient", "hang"}`.
- `TransientNodeError(Exception)`: a failure worth retrying.
- `NodeFailed(node, attempts, reason)`:
  - The message is `"<node> failed after N attempt(s): <reason>"`.
  - It keeps `.node`, `.attempts` and `.reason`.
- `NodePolicy`, a frozen dataclass:
  - `timeout_s: float`;
  - `max_attempts: int = 1`;
  - `on_failure: Literal["escalate","degrade","fallback"] = "escalate"`;
  - `backoff_s: float = 0.05`.
- `NodeRun`, a dataclass: `value`, `attempts`, `duration_ms`, `errors: list[str]`.
- `NodeFaults(faults=None)`:
  - A kind not in `NODE_FAULT_KINDS` raises
    `ValueError("unknown node fault '<kind>' for <node>; choose [...]")`.
  - Any faults with `APP_ENV=production` raise
    `RuntimeError("fault injection is disabled when APP_ENV=production")`.
  - `parse("income=transient,policy=error")` and `from_env()` (reads `NODE_FAULTS`).
  - `apply(node, attempt, policy)` does one of three things:
    - `error` raises `RuntimeError("injected error in <node>")`;
    - `transient` raises `TransientNodeError` on attempt 1 only;
    - `hang` sleeps `timeout_s × 1.5`.
- `run_node(name, fn, policy, faults=None) -> NodeRun` runs each attempt on a shared
  `ThreadPoolExecutor` (8 workers). Each attempt calls `faults.apply` and then `fn()`,
  and waits at most `timeout_s`:

  | Outcome | Error recorded | Next |
  |---|---|---|
  | success | — | return a `NodeRun` (duration so far in ms, 1 place) |
  | timeout | `"attempt N: timed out after Xs"` | retry |
  | `TransientNodeError` | `"attempt N: <msg>"` | retry |
  | any other exception | `"attempt N: <Type>: <msg>"` | raise `NodeFailed` at once: a bug isn't retried |

  Sleep `backoff_s` between attempts. When the attempts run out, raise
  `NodeFailed(name, max_attempts, last error)`.

  A timed-out attempt's thread can't be killed; its result is thrown away.

## `workflow/graph.py`: the workflow as a LangGraph `StateGraph`

```text
START → intake → income → checks → analyze → policy → agent → engine ─┬─→ END
                    │        │         │                               │
                    └────────┴─────────┴──→ escalate ──→ human_review ←┘ (MANUAL_REVIEW)
```

**`NODE_POLICIES`:**

| Node | Timeout | Attempts | On failure |
|---|---|---|---|
| `income` | 2.0 s | 2 | escalate |
| `checks` | 10.0 s | 1 | escalate |
| `analyze` | 2.0 s | 1 | escalate |
| `policy` | 3.0 s | 2 | degrade |
| `agent` | 60.0 s | 1 | fallback |
| `engine` | 1.0 s | 1 | escalate |

**`UnderwritingState`** is a `TypedDict` with `total=False`. Its keys are:
- `application`, `interactive`;
- `income`, `income_result`, `checks`, `case`;
- `proposal`, `decision`, and `failure` (`{"node","attempts","reason"}` or None);
- `audit: Annotated[list[AuditEvent], operator.add]`: append-only; a node returns only
  its new events.

**`build_graph(wf, faults=None, policies=None, checkpointer=None)`** merges `policies` over
`NODE_POLICIES` (a partial dict overrides only the nodes it names), and has these parts:

- **`guarded(name, fn, state, on_ok)`** runs `fn` under `run_node` with its policy.
  - On `NodeFailed`, it adds a `node_failure` event (with `attempts` and `on_failure`):
    - **escalate:** return `{"failure": {...}, "audit": [event]}`;
    - **degrade or fallback:** `on_ok(None, state)` with the event first in its audit.
  - On success, `on_ok(value, state)`. With more than one attempt, a `node_retry` event
    goes first.
  - Merge audit lists; never replace them.
- **The nodes.** Each calls one component through `guarded`, and returns its keys plus
  audit events:
  - `intake`: sets `failure: None`.
  - `income` (`income_verifier.verify`).
  - `checks` (`run_checks`): one `check` event per result.
  - `analyze` (`build_case` plus `run_analyzers`): one `analysis` event each.
  - `policy` (`policy_analyzer.analyze`, appended to `case.analyses`): when degraded,
    an analysis with an info `WORKFLOW_ERROR` signal,
    `"Policy retrieval unavailable; no citations attached."`
  - `agent` (`agent.recommend`): when its fallback is used, an invalid MANUAL_REVIEW
    proposal with `failure=WORKFLOW_ERROR`.
  - `engine` (`engine.decide`): builds the `UnderwritingDecision`, with
    `requires_human_review` set when the result is MANUAL_REVIEW and the full audit
    trail; event step `decision_engine`.
- **`escalate`:** a MANUAL_REVIEW decision with these fields:
  - `reason_codes=[WORKFLOW_ERROR]`, `requires_human_review=True`;
  - the existing proposal, or an invalid one saying where the workflow stopped;
  - the case metrics if a case exists.
- **`human_review`:**
  - Submits a copy of the decision to `wf.review_queue` and sets `review_case_id`.
  - When `interactive`, calls
    `interrupt({review_case_id, application_id, reason_codes, agent_proposal, question})`.
    It then validates the answer as a `HumanReview`, sets `decision.human_review`, and
    adds a `human_decision` event (actor `human:<reviewer>`).
- **Edges:**
  - From income, checks and analyze: to the next node, or to `escalate` if `failure`
    is set.
  - `policy → agent → engine` always (they degrade or fall back, never escalate).
  - From engine: to escalate if failed, to `human_review` if MANUAL_REVIEW, else END.
  - `escalate → human_review → END`.
- **Audit events.** Every event is `AuditEvent(step, actor, summary, data)`. The tests read
  the steps, actors and some data keys, so use exactly these:

  | Node | step | actor | summary | data keys |
  |---|---|---|---|---|
  | intake | `intake` | `workflow` | `Received <id>` | `documents` |
  | income | `income_verification` | `income_verification` | `Verified monthly income: <n>` | `method` |
  | checks | `check` (one per result) | `tool:<name>` | status, plus `: <reason>` if any | `required`, `latency_ms`, `attempts` |
  | analyze | `analysis` (one per analyzer) | the analyzer's `service` | `<n> signals` | `metrics`, `signals` |
  | policy | `policy_retrieval` | `wf.policy_analyzer.name` | `<n> citations` | `citations` (evidence sources; `[]` when degraded) |
  | agent | `agent` | `agent:<proposal.model>` | `Proposed <rec>: <rationale>` | `prompt_version`, `attempts`, `valid`, `validation_errors`, `input_tokens`, `output_tokens`, `tool_calls` |
  | engine | `decision_engine` | `engine:<POLICY_VERSION>` | `Decided <rec>`, plus ` (overrode agent)` | `findings` |
  | guarded | `node_failure` / `node_retry` | `node:<name>` | the error / `succeeded on attempt N` | `attempts`, `on_failure` / `errors` |
  | escalate | `escalate` | `workflow` | `Escalated: <node> failed` | the failure dict |
  | human_review | `human_review`, then `human_decision` | `review_queue`, then `human:<reviewer>` | `Escalated as <case id>`, then `Reviewer decided <rec>: <note>` | — |

  A decision's `audit_trail` is the state's audit plus the events of the node that built
  or changed it (engine, escalate, human_review), so its last steps are those events.
  `human_review` runs again from the top on resume; that's harmless, because the queue
  keys by application.
- **Compile** with `checkpointer` or `InMemorySaver(serde=_serde())`. `_serde()` is a
  `JsonPlusSerializer(allowed_msgpack_modules=[(module_name, class_name), …])` listing
  exactly the pydantic models and enums defined in `domain/models.py` (for example from
  `vars(models)` with `inspect.isclass` and `obj.__module__ == models.__name__`). Resuming deserializes saved state, so allow nothing
  else.

## Changes to earlier modules

None of yours. The given orchestrator moved its control flow into your graph.

<!-- api:start -->

## Public API

### `src/underwriter/workflow/resilience.py`

Imported elsewhere (keep these names exactly): `NodeFailed`, `NodeFaults`, `NodePolicy`, `TransientNodeError`, `run_node`

- constant `T = TypeVar('T')`
- constant `NODE_FAULT_KINDS = {'error', 'transient', 'hang'}`
- class `TransientNodeError(Exception)`
  > A failure worth retrying: the next attempt may succeed.
- class `NodeFailed(Exception)`
  - method `__init__(self, node: str, attempts: int, reason: str) -> None`
- class `NodePolicy`
  - field `timeout_s: float`
  - field `max_attempts: int = 1`
  - field `on_failure: Literal['escalate', 'degrade', 'fallback'] = 'escalate'`
  - field `backoff_s: float = 0.05`
- class `NodeRun`
  - field `value: object`
  - field `attempts: int`
  - field `duration_ms: float`
  - field `errors: list[str]`
- class `NodeFaults`
  - method `__init__(self, faults: dict[str, str] | None=None) -> None`
  - method `@classmethod parse(cls, spec: str | None) -> NodeFaults`
  - method `@classmethod from_env(cls) -> NodeFaults`
  - method `apply(self, node: str, attempt: int, policy: NodePolicy) -> None`
- function `run_node(name: str, fn: Callable[[], T], policy: NodePolicy, faults: NodeFaults | None=None) -> NodeRun`
  > Run fn under the policy. Returns a NodeRun or raises NodeFailed.

### `src/underwriter/workflow/graph.py`

Imported elsewhere (keep these names exactly): `build_graph`

Builds on: `underwriter.decision.policy`, `underwriter.domain.models`, `underwriter.workflow.resilience`

- constant `NODE_POLICIES = {'income': NodePolicy(timeout_s=2.0, max_attempts=2), 'checks': NodePolicy(timeout_s=10…`
- class `UnderwritingState(TypedDict)`
  - field `application: LoanApplication`
  - field `interactive: bool`
  - field `income: Any`
  - field `income_result: AnalysisResult`
  - field `checks: list[CheckResult]`
  - field `case: UnderwritingCase`
  - field `proposal: AgentRecommendation`
  - field `decision: UnderwritingDecision`
  - field `failure: dict | None`
  - field `audit: Annotated[list[AuditEvent], operator.add]`
- function `build_graph(wf, faults: NodeFaults | None=None, policies: dict | None=None, checkpointer=None)`
  > Compile the graph over an UnderwritingWorkflow's components.

<!-- api:end -->
