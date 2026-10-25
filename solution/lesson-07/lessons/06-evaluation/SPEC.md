# Lesson 6 spec: the eval harness (take-home)

**You build:** `src/underwriter/evaluation/harness.py`.

**Given (the seed):** the Lesson 5 reference code, plus:
- `evals/golden_cases.json` (32 cases);
- `evals/gates.json` and `evals/baseline.json`;
- the CLI command `eval [--tag] [--markdown PATH] [--update-baseline]`.

The golden cases are the spec. Their expected answers come from reading the policy, so
never edit them to make a run pass.

**Answer key:** `tests/test_eval_harness.py`, and `uv run underwriter eval`, which must
print `PASSED: 32/32 cases` with every gate passing.

```bash
uv run pytest tests/test_eval_harness.py -k "invariants or well_formed or expects_too_much"
uv run pytest && uv run underwriter eval
```

## `evaluation/harness.py`: three layers, from specific to general

1. **Expectations** per case: what this case must do.
2. **Invariants** on every case: what a credit system must never do.
3. **Gates** on the whole run: what a release must reach.

**Paths:** `EVALS` is the repo's `evals/`; `CASES`, `GATES` and `BASELINE` are the
three files in it.

**Models** (pydantic):

- `Expect`:
  - `recommendation`;
  - `reasons_include` and `reasons_exclude` (lists of codes);
  - `agent_valid` and `tool_calls`;
  - `tools_called` and `tools_rejected`;
  - `overridden`, `audit_include` and `citations_min`.

  The defaults are `None` or `[]`, which means "not checked".
- `GoldenCase`: `id`, `application`, `tags`, `scenario`, `llm_fault`, `tool_fault`,
  `node_fault`, `agent` and `expect`.
- `CaseOutcome`:
  - `id`, `tags`, `scenario`, `expected`, `actual`, `reasons`;
  - `failures`, `violations`;
  - `agent_valid`, `overridden`, `tool_calls`, `input_tokens`, `output_tokens`,
    `latency_ms`;
  - a `passed` property: no failures and no violations.

**Functions:**

- `expectation_failures(decision, expect) -> list[str]` gives one message per mismatch,
  saying what was seen and what was expected, e.g.
  `"recommendation APPROVE, expected MANUAL_REVIEW"`. The recommendation check comes
  first, so its message is always `failures[0]`. It also checks:
  - missing or unexpected reason codes;
  - agent validity;
  - the exact tool-call count;
  - tools called with outcome `ok`, and tools rejected with outcome `rejected`;
  - `overridden_by_policy` and audit steps present;
  - policy citations: `decision.agent_recommendation.evidence[*].source` values containing
    `#` (policy chunk ids), at least `citations_min`.
- `invariant_violations(decision, expected)`. Keep the first two prefixes exactly:
  `metrics()` counts them. The messages and conditions, in order:

  | Message | When |
  |---|---|
  | `"UNSAFE_APPROVAL: approved a case that should not be approved"` | recommendation APPROVE and expected isn't APPROVE |
  | `"UNFAIR_DECLINE: declined a case that policy does not decline"` | recommendation DECLINE and expected isn't DECLINE |
  | `"APPROVE without a valid proposal"` | APPROVE and `not agent_recommendation.valid` |
  | `"decision has no reason codes"` | `reason_codes` is empty |
  | `"audit trail does not start at intake"` | the trail is empty or its first step isn't `intake` |
  | `"MANUAL_REVIEW was not sent to the review queue"` | MANUAL_REVIEW and no `human_review` step in the trail |
  | `"final decision flagged for review"` | recommendation isn't MANUAL_REVIEW and `requires_human_review` is true |

  The other messages in `expectation_failures` follow the same shape:
  - `"missing reason codes [...]"`, `"unexpected reason codes [...]"`;
  - `"agent valid=<x>, expected <y>"`, `"<n> tool calls, expected <m>"`;
  - `"tools not called: [...]"`, `"tools not rejected: [...]"`;
  - `"overridden_by_policy=<x>, expected <y>"`, `"audit steps missing: [...]"`;
  - `"<n> policy citations, expected at least <m>"`.
- `load_cases(tag=None)` gives the cases, filtered by tag.
- `run_case(case)` and `run_eval(tag=None)`:
  - `run_case` builds `UnderwritingWorkflow(agent=get_agent(case.agent, case.llm_fault), faults=FaultPlan.parse(case.tool_fault), node_faults=NodeFaults.parse(case.node_fault))`
    (imports: `underwriter.agents.factory`, `underwriter.tools.faults`,
    `underwriter.workflow.orchestrator`, `underwriter.workflow.resilience`; import them
    inside the function to avoid an import cycle),
    runs the application, times it, and returns a `CaseOutcome`.
  - `run_eval` attaches the gates and, for a full run only, the baseline (`None` when
    `evals/baseline.json` is missing).

**`EvalReport(outcomes, gates, baseline=None)`:**

- `metrics()` returns these keys:
  - `cases`, `pass_rate`, `decision_accuracy`;
  - `unsafe_approvals`, `unfair_declines`, `invariant_violations`;
  - `escalation_rate`, `agent_valid_rate`, `override_rate`, `mean_tool_calls`;
  - `mean_input_tokens`, `mean_output_tokens`, `p50_latency_ms`, `p95_latency_ms`.

  Rates are rounded to 4 places, `mean_tool_calls` to 2, the token means to 1. The
  definitions:
  - `pass_rate`: the share of cases passed;
  - `decision_accuracy`: the share with actual == expected;
  - `escalation_rate`: the share whose actual is MANUAL_REVIEW;
  - `agent_valid_rate` and `override_rate`: shares of cases;
  - `unsafe_approvals` and `unfair_declines`: counts of violation strings with those
    prefixes;
  - `invariant_violations`: all violations;
  - `p50_latency_ms`: `statistics.median` (1 place);
  - `p95_latency_ms`: nearest rank on the sorted latencies,
    `lat[min(len(lat) - 1, round(0.95 * (len(lat) - 1)))]`.
- `by_tag()` gives `{tag: (passed, total)}`.
- `gate_results() -> list[(name, passed, detail)]`:

  | Gate | Passes when |
  |---|---|
  | `pass rate` | `pass_rate >= min_pass_rate` |
  | `unsafe approvals` | `unsafe_approvals <= max_unsafe_approvals` |
  | `unfair declines` | `unfair_declines <= max_unfair_declines` |
  | `invariants` | `invariant_violations <= max_invariant_violations` |
  | `p95 latency` | `p95_latency_ms <= max_p95_latency_ms` |
  | `mean input tokens` | `mean_input_tokens <= max_mean_input_tokens` |

  With a baseline of the same size, two more:

  | Gate | Passes when |
  |---|---|
  | `tokens vs baseline` | the growth in mean input tokens is `<= max_token_increase_vs_baseline` |
  | `pass rate vs baseline` | `pass_rate >=` the baseline's |

  The details are exactly these:
  - `"{pass_rate:.0%} ≥ {min:.0%}"` and `"{n} ≤ {max}"` for the counts;
  - `"{n} violations ≤ {max}"`;
  - `"{p95:.0f} ms ≤ {max} ms"`;
  - `"{tokens:.0f} ≤ {max}"`;
  - growth `(now − base) / base` as `"{growth:+.1%} ≤ +{limit:.0%} (baseline {base:.0f})"`;
  - `"{now:.0%} vs {base:.0%}"`.

  "Same size" means `baseline["cases"] == metrics()["cases"]`.
- `passed` (a property): every gate passed.
- `markdown()` starts with `## Eval report`, then a gates table with the rows
  `| <gate> | pass |` or `| <gate> | **FAIL** |` plus the detail, then a metrics table
  `| <metric> | <value> |`, then `### Failing cases` (if any) with `- **<id>** <scenario>: <failures>`.
  CI will post it in Lesson 9.

**Printing and the baseline:**

- `print_report(report)`:
  - one line per case;
  - the families;
  - a one-line metrics summary;
  - the gates;
  - `PASSED|FAILED: n/N cases`.
- `write_baseline(report)` writes the stable metrics:
  - `cases`, `pass_rate`, `decision_accuracy`;
  - `escalation_rate`, `agent_valid_rate`, `override_rate`;
  - `mean_tool_calls`, `mean_input_tokens`, `mean_output_tokens`.

## Changes to earlier modules

None.

<!-- api:start -->

## Public API

### `src/underwriter/evaluation/harness.py`

Imported elsewhere (keep these names exactly): `CASES`, `EvalReport`, `invariant_violations`, `load_cases`, `print_report`, `run_case`, `run_eval`, `write_baseline`

Builds on: `underwriter.domain.models`, `underwriter.ingestion.documents`

- constant `EVALS = Path(__file__).resolve().parents[3] / 'evals'`
- constant `CASES = EVALS / 'golden_cases.json'`
- constant `GATES = EVALS / 'gates.json'`
- constant `BASELINE = EVALS / 'baseline.json'`
- class `Expect(BaseModel)`
  - field `recommendation: Recommendation`
  - field `reasons_include: list[str] = []`
  - field `reasons_exclude: list[str] = []`
  - field `agent_valid: bool | None = None`
  - field `tool_calls: int | None = None`
  - field `tools_called: list[str] = []`
  - field `tools_rejected: list[str] = []`
  - field `overridden: bool | None = None`
  - field `audit_include: list[str] = []`
  - field `citations_min: int | None = None`
- class `GoldenCase(BaseModel)`
  - field `id: str`
  - field `application: str`
  - field `tags: list[str]`
  - field `scenario: str`
  - field `llm_fault: str | None = None`
  - field `tool_fault: str | None = None`
  - field `node_fault: str | None = None`
  - field `agent: str | None = None`
  - field `expect: Expect`
- class `CaseOutcome(BaseModel)`
  - field `id: str`
  - field `tags: list[str]`
  - field `scenario: str`
  - field `expected: str`
  - field `actual: str`
  - field `reasons: list[str]`
  - field `failures: list[str] = Field(default=[], description='expectations not met')`
  - field `violations: list[str] = Field(default=[], description='invariants broken')`
  - field `agent_valid: bool`
  - field `overridden: bool`
  - field `tool_calls: int`
  - field `input_tokens: int`
  - field `output_tokens: int`
  - field `latency_ms: float`
  - method `@property passed(self) -> bool`
- function `expectation_failures(d: UnderwritingDecision, e: Expect) -> list[str]`
- function `invariant_violations(d: UnderwritingDecision, expected: Recommendation) -> list[str]`
  > Properties that must hold for every case, whatever the case expects.
- function `load_cases(tag: str | None=None) -> list[GoldenCase]`
- function `run_case(case: GoldenCase) -> CaseOutcome`
- class `EvalReport(BaseModel)`
  - field `outcomes: list[CaseOutcome]`
  - field `gates: dict`
  - field `baseline: dict | None = None`
  - method `metrics(self) -> dict`
  - method `by_tag(self) -> dict[str, tuple[int, int]]`
  - method `gate_results(self) -> list[tuple[str, bool, str]]`
  - method `@property passed(self) -> bool`
  - method `markdown(self) -> str`
- function `run_eval(tag: str | None=None) -> EvalReport`
- function `print_report(r: EvalReport) -> None`
- function `write_baseline(r: EvalReport) -> None`

<!-- api:end -->
