# Lesson 3 spec: the LLM agent, structured output and validation

**You build:** three modules in `src/underwriter/agents/`:
- `context.py`
- `validation.py`
- `underwriting.py`

**Given (the seed):** the Lesson 2 reference code, plus:
- the LLM port `llm/client.py` (`LLMClient`, `Message`, `LLMResponse`, `LLMUnavailable`);
- `llm/mock.py`, a deterministic mock model with faults: `malformed`, `bad_citation`,
  `wrong_number`, `unavailable`, and each with `_always`;
- `llm/config.py` and `llm/litellm_client.py` (an optional live provider);
- the prompt `agents/prompts/underwriting_v1.md`;
- the orchestrator wiring, and the Lesson 3 additions in `domain/models.py`.

**Answer key:** `tests/test_llm_agent.py`, plus `run-all` (8/8). The workflow tests stay
red until all three modules work, because the workflow calls the agent.

```bash
uv run pytest tests/test_llm_agent.py -k context
uv run pytest tests/test_llm_agent.py -k "semantic or threshold or parse"
uv run pytest                      # whole suite once the agent works
uv run underwriter prompt data/applications/APP-006.json    # read what the model sees
```

## `context.py`: decide exactly what the model sees

**Rules:**
1. Minimise: no name, date of birth, ID digits, email or address ever.
2. Give everything an id the model must cite.
3. Prioritise within a budget.

**Constants:**
- `MAX_CONTEXT_CHARS = 6000`;
- `EXCERPT_CHARS = 360`;
- `RATIO_METRICS = {"post_loan_dti", "income_discrepancy", "loan_to_annual_income"}`.

**`CaseContext`** is a pydantic model:
- `payload: dict`;
- `allowed_ids: dict[str, str]` (id → short description);
- `dropped_policy: int = 0`;
- a property `as_json`, which is `json.dumps(payload, indent=1, ensure_ascii=False)`.

**`build_context(case, max_chars=MAX_CONTEXT_CHARS)`** builds `payload` with these keys,
in this order:

- `application`:
  - `application_id`, `loan` (`model_dump()`), `employment_type`;
  - `stated_annual_income`, `existing_monthly_debt_payments`.
- `signals`: one `{"id": "signal:<CODE>", "code", "severity", "message"}` per signal in
  `case.all_signals`.
- `metrics`: `{name: {"id": "metric:<name>", "value", "unit"}}`, sorted by name. `unit`
  is `"fraction"` for `RATIO_METRICS`, else `None`.
- `policy`: from analyses whose `service == "policy_analysis"`, one
  `{"id": e.source, "citation", "excerpt"}` per evidence item.
  - `e.detail` is `"<citation>: <text>"`; split it at the first `": "` (`partition`). A
    detail with no `": "` becomes the citation, with an empty excerpt.
  - The excerpt is the text cut to `EXCERPT_CHARS`.
- `documents`: one `{"id": "doc:<path>", "type": <doc_type value>}` per document.

`allowed_ids` maps every id to a short description: the signal's message,
`"name = value"`, the doc type, or the citation.

**Budget:** while `as_json` is longer than `max_chars` **and policy excerpts remain**, drop
the last policy excerpt (and its id from `allowed_ids`) and count it in
`dropped_policy`. Never drop signals or metrics. If they alone are over budget, stop:
the context is returned as it is.

Two kinds of order apply here:
- **The payload's key order** (`application` first) is the order the model reads.
- **The module docstring's priority** (signals, then metrics, then policy, then the
  summary) is what gets cut last when space runs out. Only policy excerpts are ever cut.

Two signals with the same code share one id; keep both in `signals`. Write values in
`allowed_ids` as `f"{name} = {value}"`.

## `validation.py`: a reply that parses isn't yet an answer you can use

**Constants:**
- `RATIO_TOLERANCE = 0.0005` (for fractions);
- `PERCENT_TOLERANCE = 0.15` (percentage points, for numbers written in prose).

**`UnderwritingOutput`** is a pydantic model with `extra="forbid"`:
- `recommendation`: `Literal["APPROVE","DECLINE","MANUAL_REVIEW"]`;
- `rationale`: str, at most 800 characters;
- `risk_factors: list[str] = []` and `missing_information: list[str] = []`;
- `evidence`: list[str], at least 1 item;
- `figures: dict[str, float] = {}`.

**`parse_output(text)`** returns an `UnderwritingOutput`. It removes ```` ``` ```` and ```` ```json ```` fences
(regex ```` ```(?:json)? ````),
then takes the text from the first `{` to the last `}`. Each failure raises `ValueError`:

| Failure | Message |
|---|---|
| no `{`, or no `}` after it (a reply cut short) | `"no JSON object found in the reply"` |
| bad JSON | `"reply is not valid JSON: <exc.msg>"` |
| schema | `"reply does not match the schema: "` + `"; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}")` over pydantic's errors |

**`semantic_errors(out, ctx)`** returns a list of plain-English errors, `[]` if valid.
Each one goes back to the model in the repair turn:

1. Unknown evidence ids: `"evidence cites ids not in the context: [...]"`.
2. Figures:
   - a name that isn't a metric gives `"figures.<name> is not a metric in the context"`;
   - a wrong value gives `"figures.<name> = <value> but the fact is <actual>"`. The
     tolerance is `RATIO_TOLERANCE` for ratio metrics, 0.5 otherwise.
3. Every percentage in the rationale (regex `(\d+(?:\.\d+)?)\s*%`, so "43%" and "45.6%")
   must match one of these, or it gives
   `"rationale states <pct>% which matches no fact in the context"` (`<pct>` as written):
   - a ratio metric × 100, within `PERCENT_TOLERANCE`;
   - exactly a percentage that appears in a policy excerpt of the payload (what the model
     saw; e.g. "above 43%").
4. Missing information with any recommendation but MANUAL_REVIEW:
   `"information is missing but the recommendation is not MANUAL_REVIEW"`.
5. APPROVE while any signal has severity `review`:
   `"APPROVE despite open review signals: [codes]"`.

Lists in messages use Python's list repr, in the order given. A value exactly at a
tolerance passes: an error needs `abs(diff) > tolerance`.

## `underwriting.py`: propose, validate, repair once, fail safe

**Constants and helpers:**
- `PROMPT_VERSION = "underwriting-v1"`;
- `SYSTEM_PROMPT`, read from `prompts/underwriting_v1.md`;
- `MAX_ATTEMPTS = 2` (one answer plus one repair);
- `build_messages(case)` returns `([system, user], ctx)`, where `ctx` is the
  `CaseContext`. The Public API shows the return type as `object`; it is a `CaseContext`. The user message is
  `"Assess this application. Reply with the JSON object only.\n<case_json>\n{ctx.as_json}\n</case_json>"`.
  The mock model reads only that block.

**`LLMUnderwritingAgent(client)`** stores `client`, and `model = client.model`.

`recommend(case)` runs the loop:

- Up to `MAX_ATTEMPTS` times, call
  `client.complete(messages, max_output_tokens=600, json_mode=True)`.
  - `LLMUnavailable`: fall back at once with `MODEL_UNAVAILABLE`,
    `attempts=<this attempt>` and `validation_errors=[str(exc)]`. No retry: an outage
    isn't fixed by asking again.
  - Add up the input and output tokens across attempts.
  - `parse_output`, then `semantic_errors`. A `ValueError` from parsing is one error.
  - **Valid:** return an `AgentRecommendation` with:
    - `recommendation`, `rationale`, `risk_factors`, `missing_information`;
    - `evidence=[Evidence(source=id, detail=ctx.allowed_ids[id])]`;
    - `model=resp.model`, `prompt_version=PROMPT_VERSION`, `attempts=<this attempt>`,
      and the token totals.
  - **Invalid:** append the reply as an `assistant` message, and a `user` message
    listing the errors and asking for the corrected JSON only.
- Still invalid: fall back with `INVALID_MODEL_OUTPUT` and `attempts=MAX_ATTEMPTS`.

A fallback is a MANUAL_REVIEW proposal with:
- `model=self.model` and `prompt_version=PROMPT_VERSION` (without them the record would
  say `rules-stub-v1`);
- `valid=False`, `failure=<code>`, `validation_errors=<errors>`;
- `missing_information=["A valid model recommendation"]`;
- the token totals;
- a rationale saying a human must decide.

## Changes to earlier modules

The seed engine in this starter already has this rule. You only need it if you carried
your own Lesson 1 engine forward; add it at the start of `DecisionEngine.decide`, after
`evaluate_policy`:

- When `proposal.valid` is false, add a finding with code
  `proposal.failure or ReasonCode.INVALID_MODEL_OUTPUT`, outcome MANUAL_REVIEW, section
  `"9.1"`, and message `"Agent output unusable: "` plus the first three validation
  errors.
- A failed model is not evidence of anything, so a human decides. Policy declines still
  stand (APP-005).

<!-- api:start -->

## Public API

### `src/underwriter/agents/context.py`

Imported elsewhere (keep these names exactly): `build_context`

Builds on: `underwriter.domain.models`

- constant `MAX_CONTEXT_CHARS = 6000`
- constant `EXCERPT_CHARS = 360`
- constant `RATIO_METRICS = {'post_loan_dti', 'income_discrepancy', 'loan_to_annual_income'}`
- class `CaseContext(BaseModel)`
  - field `payload: dict`
  - field `allowed_ids: dict[str, str]`
  - field `dropped_policy: int = 0`
  - method `@property as_json(self) -> str`
- function `build_context(case: UnderwritingCase, max_chars: int=MAX_CONTEXT_CHARS) -> CaseContext`

### `src/underwriter/agents/validation.py`

Imported elsewhere (keep these names exactly): `UnderwritingOutput`, `parse_output`, `semantic_errors`

Builds on: `underwriter.agents.context`

- constant `RATIO_TOLERANCE = 0.0005`
- constant `PERCENT_TOLERANCE = 0.15`
- class `UnderwritingOutput(BaseModel)`
  - field `recommendation: Literal['APPROVE', 'DECLINE', 'MANUAL_REVIEW']`
  - field `rationale: str = Field(max_length=800)`
  - field `risk_factors: list[str] = []`
  - field `missing_information: list[str] = []`
  - field `evidence: list[str] = Field(min_length=1)`
  - field `figures: dict[str, float] = {}`
- function `parse_output(text: str) -> UnderwritingOutput`
  > Parse model text into the schema, tolerating code fences and chatter.
- function `semantic_errors(out: UnderwritingOutput, ctx: CaseContext) -> list[str]`

### `src/underwriter/agents/underwriting.py`

Imported elsewhere (keep these names exactly): `LLMUnderwritingAgent`, `PROMPT_VERSION`, `build_messages`

Builds on: `underwriter.agents.context`, `underwriter.agents.validation`, `underwriter.domain.models`, `underwriter.llm.client`

- constant `PROMPT_VERSION = 'underwriting-v1'`
- constant `SYSTEM_PROMPT = (Path(__file__).parent / 'prompts' / 'underwriting_v1.md').read_text()`
- constant `MAX_ATTEMPTS = 2`
- function `build_messages(case: UnderwritingCase) -> tuple[list[Message], object]`
- class `LLMUnderwritingAgent`
  - method `__init__(self, client: LLMClient) -> None`
  - method `recommend(self, case: UnderwritingCase) -> AgentRecommendation`

<!-- api:end -->
