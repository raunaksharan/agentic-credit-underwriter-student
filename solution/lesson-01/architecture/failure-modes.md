# Failure modes

Designed for in lesson 1, tested in lesson 6, observed in lesson 7, hardened in lesson 8.

| # | Failure | Where | Impact if unhandled | Designed response | Sample case |
|---|---|---|---|---|---|
| F1 | Credit bureau has no record / times out | Bureau tool | Agent invents or assumes a score | `CreditDataUnavailable` → `CREDIT_DATA_UNAVAILABLE` → manual review | APP-003 |
| F2 | Required document missing | Ingestion | DTI computed on stated income | `MISSING_DOCUMENT` + `INCOME_UNVERIFIED`; DTI not computed | APP-007 |
| F3 | Stated vs verified income conflict | Income verification | Over-lending | `INCOME_MISMATCH` above 15% → manual review | APP-004 |
| F4 | Name on documents ≠ applicant | Fraud checks | Identity fraud approved | `IDENTITY_MISMATCH` → manual review, never auto-decline | APP-006 |
| F5 | Agent proposes something policy forbids | Agent | Policy breach | Engine overrides; `overridden_by_policy=true` logged | APP-008 |
| F6 | Agent declines outside policy | Agent | Unfair, unexplainable decline | Converted to manual review | unit test |
| F7 | LLM returns malformed output | Agent (L3) | Pipeline crash or silent garbage | Schema validation, retry, then escalate | lesson 6 |
| F8 | Retrieval returns irrelevant policy | RAG (L2) | Wrong citation, wrong explanation | Retrieval evals; engine thresholds don't depend on retrieval | lesson 2 |
| F9 | Extraction misreads a number | Document AI (L3) | Wrong DTI | Cross-check payslip vs bank deposits; confidence thresholds | lesson 3 |
| F10 | Slow dependency | Any tool | Latency SLO breach | Timeouts, concurrency, graceful degradation | lesson 8 |

**Rule of thumb:** for every component, ask "what does the system do when this
returns nothing, returns garbage, or never returns?" If the answer is "it guesses",
the design is wrong.
