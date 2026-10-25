# Lesson 4 spec: typed external checks and a bounded tool-using agent

**You build:**
- `src/underwriter/tools/checks.py`;
- `src/underwriter/agents/tools.py`;
- `src/underwriter/agents/tool_agent.py`.

**Given (the seed):** the Lesson 3 reference code, plus:
- `tools/faults.py`:
  - the errors `ToolError`, `ToolTimeout`, `ToolServerError`, `ToolRateLimited`,
    `ToolMalformed` and `ToolNoRecord`;
  - `FaultPlan`, with `parse`, `for_tool`, `latency_ms` and `raise_if_faulted`; it is
    refused when `APP_ENV=production`.
- `tools/bureau.py` and `ingestion/documents.py` (`DocumentStore`);
- `agents/factory.py`, the prompt `agents/prompts/underwriting_agent_v1.md`, the mock
  model's tool mode (faults `loop` and `disallowed_tool`), and the services and
  orchestrator wiring.

**Answer key:** `tests/test_tools_and_agent.py`, the whole suite, and `run-all` (8/8).

```bash
uv run pytest tests/test_tools_and_agent.py -k "typed or faults_map or no_bureau"   # checks
uv run pytest tests/test_tools_and_agent.py -k toolbox                             # tools
uv run pytest                                                                    # the loop
```

## `tools/checks.py`: every outcome is a typed result

- `CheckSpec(name, required, description, fn)` is a frozen dataclass; `fn` takes a
  `LoanApplication` and returns a dict.
- **The fake tools.** Each reads the synthetic data the way a real integration would
  read an API, using module-level `FileCreditBureau()` and `DocumentStore()`.

  | Tool | Required | Returns | Fails with |
  |---|---|---|---|
  | `credit_bureau` | yes | the bureau report for the applicant's ID digits and name (`model_dump()`) | `ToolNoRecord("credit bureau has no record for this applicant")` when the bureau has none. Never pass the bureau's own message on: it can contain ID digits |
  | `fraud_screen` | yes | `{"identity_risk": "low" if the email ends in @example.com/@example.org else "medium", "watchlist_hit": False, "vendor": "fake-fraud-v1"}` | — |
  | `bank_data` | no | from the bank-statement CSV: `months`, `avg_monthly_payroll_deposits` (rows whose description contains PAYROLL, divided by distinct months, 2 places), `lowest_balance`, `overdrafts` (rows with a negative balance) | `ToolNoRecord("no bank statement on file")` |
  | `employment_verification` | no | `{"verified": employer name appears in the employment letter, "source": "employment_letter", "employer"}`, or `verified: False, source: "none"` when there's no letter | — |

- `CHECKS` is the four `CheckSpec`s in that order, with short descriptions.
- Validators live in a module dict `_VALIDATORS = {"credit_bureau": <validate as CreditProfile>}`
  keyed by tool name; `CheckSpec` has no validator field.
- `bank_data` details:
  - `months` is the number of distinct `YYYY-MM` prefixes of the `date` column;
  - PAYROLL matching is case-sensitive on `description`;
  - a statement with no rows is no record: raise `ToolNoRecord("bank statement has no transactions")`.
    No sample has an empty statement; the reference code doesn't handle one, and never
    defaulting to 0 is the rule.
- `employment_verification` checks whether the employer name, as written in the
  application, appears in the letter's text; "no letter" means the application has no
  `employment_letter` document.
- **`run_check(spec, app, faults=None) -> CheckResult`.** It never returns None and
  never raises. Using `faults = faults or FaultPlan()`, and timing with `perf_counter`:
  1. Sleep `faults.latency_ms(name)` milliseconds.
  2. Call `faults.raise_if_faulted(name)`.
  3. Set `data = spec.fn(app)`.
  4. If `faults.for_tool(name) == "malformed"`, replace `data` with
     `{"unexpected": "payload", "score": "seven hundred"}`.
  5. Run the validator. A pydantic `ValidationError` raises
     `ToolMalformed("<name>: response failed validation (N errors)")`.

  The exception decides the status:

  | Raised | Status | Reason |
  |---|---|---|
  | `ToolMalformed` | INVALID | its message |
  | `ToolRateLimited` | UNAVAILABLE | `"<msg> (retry after <retry_after_s>s)"` |
  | any other `ToolError` | UNAVAILABLE | its message |
  | nothing | OK | (with `data`) |

  Every result carries `tool`, `required`, `data` (`{}` for every failure), `reason`, and
  `latency_ms` (milliseconds from `perf_counter`, rounded to 2 places). A malformed answer is never OK: a score of "seven hundred" must not reach
  the engine.
- **`run_checks(app, faults=None, specs=None)`** runs every spec in `CHECKS`, in order.

## `agents/tools.py`: the allow-list is the security boundary

The agent can look things up and ask for documents. It can't decide, change data, or
call anything not listed.

**The argument models** (pydantic, `extra="forbid"`):
- `CheckPolicyArgs(query: str, 3–300 chars)`;
- `RequestDocumentArgs(doc_type: DocumentType, reason: str, 3–300 chars)`;
- `CheckResultArgs(tool: str)`.

**`AgentTool(name, description, args, fn)`** has `schema_line()`, which gives
`"- name(param: type, …): description"`, using the args model's JSON-schema properties.

**`ToolBox(tools, new_ids={}, requested_documents=[])`**:
- `describe()` is one schema line per tool.
- `call(name, arguments) -> (ok, result)` never raises:
  - unknown tool: `(False, {"error": "tool '<name>' is not allowed; allowed: [sorted names]"})`;
  - bad arguments: `(False, {"error": "bad arguments for <name>: N errors", "details": <first 3 pydantic errors as JSON>})`;
  - otherwise `(True, tool.fn(validated_args))`.

**`build_toolbox(case, retriever)`** builds three tools, each recording the citable ids
it produced in `box.new_ids`:
- `check_policy`:
  - Calls `retriever.retrieve(query, k=3)`.
  - Abstained gives `{"abstained": True, "reason"}`.
  - Otherwise `{"results": [{"id": chunk_id, "citation", "excerpt": text[:300]}]}`.
- `request_missing_document`:
  - Records `{"doc_type", "reason"}` in `requested_documents`.
  - The id is `request:<doc_type>`.
  - Returns `{"id", "status": "queued for the applicant"}`.
- `get_check_result`:
  - Unknown gives `{"error": "no check named <tool>", "available": [...]}`.
  - Otherwise the id is `check:<tool>` and it returns `{"id", "status", "reason", "data"}`.

## `agents/tool_agent.py`: a loop that's safe to leave unattended

**Constants:**
- `PROMPT_VERSION = "underwriting-agent-v1"`;
- `MAX_TOOL_CALLS = 4`;
- `MAX_REPAIRS = 1`;
- `DEADLINE_S = float(os.environ.get("AGENT_DEADLINE_S", "30"))`.

**`parse_action(text) -> dict`** takes one JSON object from the first `{` to the last
`}`, and raises `ValueError` in each of these cases:

| Failure | Message |
|---|---|
| no braces | `"no JSON object found in the reply"` |
| bad JSON | `"reply is not valid JSON: <msg>"` |
| any other `action` | `'"action" must be "call_tool" or "final"'` |

**`ToolUsingUnderwritingAgent(client, retriever=None, max_tool_calls=MAX_TOOL_CALLS, deadline_s=DEADLINE_S, clock=time.monotonic)`**:

- `build_messages(case)` returns `(messages, ctx, box)`, where `box` is the `ToolBox` (the
  Public API shows it as `object`):
  - The system message is the prompt template
    (`agents/prompts/underwriting_agent_v1.md`, read once at import into `_TEMPLATE`).
    `{max_steps}` and `{tools}` (`box.describe()`) are filled with `str.replace`. Not
    `str.format`: the template contains literal JSON braces.
  - The user message is `"Assess this application. Use tools if they help, then give your final answer.\n<case_json>\n…\n</case_json>"`.
- `recommend(case)` runs the loop:
  1. **Deadline:** read `started = self.clock()` once before the loop, and
     `self.clock()` once at the top of each iteration. Past `deadline_s`, fall back with
     AGENT_LIMIT_REACHED, `f"deadline of {self.deadline_s:.0f}s exceeded"`. The tests'
     clock advances on every read, so read it exactly that often.
  2. **Call the model:** `client.complete(messages, max_output_tokens=700, json_mode=True)`.
     - `LLMUnavailable` falls back with MODEL_UNAVAILABLE.
     - Count the call and its tokens, and append the reply as an `assistant` message.
  3. **Parse:** `parse_action`. A `ValueError` gets one repair (a `user` message naming
     the problem); after that, fall back with INVALID_MODEL_OUTPUT. One repair budget
     (`MAX_REPAIRS`) is shared by parse errors and validation errors. `parse_action`
     strips nothing: it takes the first `{` to the last `}`.
  4. **`call_tool`:**
     - Already at `max_tool_calls`: fall back with AGENT_LIMIT_REACHED
       (`"tool budget of N calls exhausted"`).
     - Otherwise run `box.call(tool, arguments or {})`, and record
       `{"tool", "arguments", "outcome": "ok"|"rejected", "detail": error or ""}`.
     - Send the result back as a `user` message, exactly
       `f'<tool_result name="{name}">\n{json.dumps(result)}\n</tool_result>'`. The mock
       model matches those newlines.
     - The tool cap counts every record, rejected calls included.
  5. **`final`:**
     - Validate `parse_output(json.dumps(action.get("answer", {})))` and `semantic_errors`,
       against the
       context with `allowed_ids` extended by `box.new_ids`.
     - **Valid:** an `AgentRecommendation` as in Lesson 3, with `attempts=<model calls>`
       and `tool_calls=<the records>`. Each requested document is added to
       `missing_information` as `"<doc_type> (requested)"`, unless it's already listed.
     - **Invalid:** one repair, then fall back with INVALID_MODEL_OUTPUT.

Every fallback is MANUAL_REVIEW with `valid=False`, the reason code, the errors, the
token totals and the tool-call records. The engine still decides.

## Changes to earlier modules

None of yours. The given services and orchestrator now read check results; see
`workflow/services.py` (`ChecksAnalyzer`).

<!-- api:start -->

## Public API

### `src/underwriter/tools/checks.py`

Imported elsewhere (keep these names exactly): `CHECKS`, `CheckSpec`, `run_check`, `run_checks`

Builds on: `underwriter.domain.models`, `underwriter.ingestion.documents`, `underwriter.tools.bureau`, `underwriter.tools.faults`

- class `CheckSpec`
  - field `name: str`
  - field `required: bool`
  - field `description: str`
  - field `fn: Callable[[LoanApplication], dict]`
- function `credit_bureau(app: LoanApplication) -> dict`
- function `bank_data(app: LoanApplication) -> dict`
- function `employment_verification(app: LoanApplication) -> dict`
- function `fraud_screen(app: LoanApplication) -> dict`
- constant `CHECKS = [CheckSpec('credit_bureau', True, 'Bureau credit report (score, delinquencies, debt)', …`
- function `run_check(spec: CheckSpec, app: LoanApplication, faults: FaultPlan | None=None) -> CheckResult`
  > Call one tool. Every exception becomes a typed status, never a missing value.
- function `run_checks(app: LoanApplication, faults: FaultPlan | None=None, specs: list[CheckSpec] | None=None) -> list[CheckResult]`
  > All checks, one after another. Lesson 8 makes this concurrent.

### `src/underwriter/agents/tools.py`

Imported elsewhere (keep these names exactly): `build_toolbox`

Builds on: `underwriter.domain.models`, `underwriter.rag.retriever`

- class `CheckPolicyArgs(BaseModel)`
  - field `query: str = Field(min_length=3, max_length=300)`
- class `RequestDocumentArgs(BaseModel)`
  - field `doc_type: DocumentType`
  - field `reason: str = Field(min_length=3, max_length=300)`
- class `CheckResultArgs(BaseModel)`
  - field `tool: str`
- class `AgentTool`
  - field `name: str`
  - field `description: str`
  - field `args: type[BaseModel]`
  - field `fn: Callable[[BaseModel], dict]`
  - method `schema_line(self) -> str`
- class `ToolBox`
  > The tools for one case, plus everything they produced (for citations and audit).
  - field `tools: dict[str, AgentTool]`
  - field `new_ids: dict[str, str] = field(default_factory=dict)`
  - field `requested_documents: list[dict] = field(default_factory=list)`
  - method `describe(self) -> str`
  - method `call(self, name: str, arguments: dict) -> tuple[bool, dict]`
    > Returns (ok, result). Unknown tools and bad arguments are errors, not crashes.
- function `build_toolbox(case: UnderwritingCase, retriever: PolicyRetriever) -> ToolBox`

### `src/underwriter/agents/tool_agent.py`

Imported elsewhere (keep these names exactly): `ToolUsingUnderwritingAgent`, `parse_action`

Builds on: `underwriter.agents.context`, `underwriter.agents.tools`, `underwriter.agents.validation`, `underwriter.domain.models`, `underwriter.llm.client`, `underwriter.rag.retriever`

- constant `PROMPT_VERSION = 'underwriting-agent-v1'`
- constant `MAX_TOOL_CALLS = 4`
- constant `MAX_REPAIRS = 1`
- constant `DEADLINE_S = float(os.environ.get('AGENT_DEADLINE_S', '30'))`
- function `parse_action(text: str) -> dict`
  > One JSON object with an action. Raises ValueError with a message for the model.
- class `ToolUsingUnderwritingAgent`
  - method `__init__(self, client: LLMClient, retriever: PolicyRetriever | None=None, max_tool_calls: int=MAX_TOOL_CALLS, deadline_s: float=DEADLINE_S, clock: Callable[[], float]=time.monotonic) -> None`
  - method `build_messages(self, case: UnderwritingCase) -> tuple[list[Message], CaseContext, object]`
  - method `recommend(self, case: UnderwritingCase) -> AgentRecommendation`

<!-- api:end -->
