# Failure modes

Designed for in lesson 1, tested in lesson 6, observed in lesson 7, hardened in lesson 8.

| # | Failure | Where | Impact if unhandled | Designed response | Sample case |
|---|---|---|---|---|---|
| F1 | Credit bureau has no record / times out | Bureau tool | Agent invents or assumes a score | Typed `CheckResult` UNAVAILABLE/INVALID → `CREDIT_DATA_UNAVAILABLE` → manual review | APP-003, `--tool-fault credit_bureau=timeout` |
| F2 | Required document missing | Ingestion | DTI computed on stated income | `MISSING_DOCUMENT` + `INCOME_UNVERIFIED`; DTI not computed | APP-007 |
| F3 | Stated vs verified income conflict | Income verification | Over-lending | `INCOME_MISMATCH` above 15% → manual review | APP-004 |
| F4 | Name on documents ≠ applicant | Fraud checks | Identity fraud approved | `IDENTITY_MISMATCH` → manual review, never auto-decline | APP-006 |
| F5 | Agent proposes something policy forbids | Agent | Policy breach | Engine overrides; `overridden_by_policy=true` logged | APP-008 |
| F6 | Agent declines outside policy | Agent | Unfair, unexplainable decline | Converted to manual review | unit test |
| F7 | LLM returns malformed or wrong output | Agent (L3) | Workflow crash or silent garbage | Schema + semantic validation, one repair, then `INVALID_MODEL_OUTPUT` → review | `--llm-fault malformed_always` |
| F11 | LLM provider down or over quota | Agent (L3) | Workflow crash | `LLMUnavailable` → `MODEL_UNAVAILABLE` → review; policy declines still stand | `--llm-fault unavailable` |
| F12 | Required check fails (fraud screen 500, 429) | Tools (L4) | Decision made without a required check | `CHECK_UNAVAILABLE` → review; optional checks (bank, employment) degrade to info | `--tool-fault fraud_screen=server_error` |
| F13 | Agent loops, overruns, or calls a tool it shouldn't | Agent (L4) | Runaway cost, unauthorised action | Allow-list refuses unknown tools; step cap and deadline → `AGENT_LIMIT_REACHED` → review | `--llm-fault loop`, `--llm-fault disallowed_tool` |
| F14 | A workflow step crashes or hangs | Workflow (L5) | Request lost, or a decision without a step | Per-node timeout and retry (transient only); required steps → `WORKFLOW_ERROR` → human; policy retrieval degrades, logged | `--node-fault income=error`, `analyze=hang` |
| F15 | Reviewer decision not recorded | Human review (L5) | Unauditable override | Graph pauses with `interrupt()`; `HumanReview` (reviewer, decision, note) validated and appended to the audit | `--review-as APPROVE` |
| F16 | Personal data leaks into prompts or telemetry | Context, traces (L7) | Privacy breach in a third-party model or tracing vendor | Messages carry no names or ids; evidence detail goes only to the audit; free-text span attributes redacted; PII tests over every sample | `test_no_personal_data_in_any_span`, `test_no_application_leaks_personal_data_into_context` |
| F17 | Nobody can say why a decision was slow or expensive | Operations (L7) | Cost and latency regress unnoticed | One root span per decision; node, check, retrieval, LLM and tool spans with GenAI token attributes; `usage` (tokens, cost, step times) on every decision | `underwriter trace APP-002.json` |
| F8 | Retrieval returns irrelevant policy | RAG (L2) | Wrong citation, wrong explanation | Retrieval evals; engine thresholds don't depend on retrieval | lesson 2 |
| F9 | Extraction misreads a number | Document AI (L3) | Wrong DTI | Cross-check payslip vs bank deposits; confidence thresholds | lesson 3 |
| F10 | Slow or flaky dependency | Tools (L8) | Latency SLO breach; a hung decision; a 500 that would have succeeded on retry | Checks run concurrently under one deadline (3 s); a check that misses it is `UNAVAILABLE` ("deadline of 3.0s exceeded") and the lesson 4 rules escalate or degrade; transient errors (timeout, 429, 500) retried with full-jitter backoff, `Retry-After` honoured, never past the deadline | `--tool-fault credit_bureau=latency:3500`, `credit_bureau=flaky:1`; G-R01–G-R03 |

**Rule of thumb:** for every component, ask "what does the system do when this
returns nothing, returns garbage, or never returns?" If the answer is "it guesses",
the design is wrong.
