# CLAUDE.md: agentic-credit-underwriter

An FDE Academy course repo: an agentic credit underwriting platform for a fictional
lender, Meridian Digital Lending. Students build it lesson by lesson, often with you.
Your job is to help them ship code that passes the tests and the eval, and that they
can explain.

## Context

- **The business.** Meridian lends unsecured personal loans ($1k–$50k) online. Today
  underwriters spend about 45 minutes per application gathering facts. The system
  gathers and checks the facts, an agent proposes, a deterministic engine decides, and
  anything uncertain goes to a human. Read `architecture/requirements.md` first.
- **The decisions already made** are the ADRs in `architecture/adr/`: hybrid AI plus
  deterministic code (0001), the agent proposes and the engine decides (0002), and
  escalate, never guess (0003). Failure modes F1–F17 are in
  `architecture/failure-modes.md`.
- **The sources of truth:** policy thresholds in `decision/policy.py` (from
  `data/policies/`), regulation in `data/corpus/` (real US federal documents), and
  expected outcomes in `data/expected_outcomes.json` and `evals/golden_cases.json`.
- **Where a lesson is specified:** `lessons/NN-*/SPEC.md` (what to build: public API,
  behaviour, exact messages), `PROMPTS.md` (how to build it with you) and `README.md`
  (the lesson). Repeatable procedures are in `workflows/`.

## Scope

- **In scope:** the AI-engineering spine. That is the risk and decision engine, RAG
  over policy and regulation, the LLM agent with validation, typed tools with fault
  injection, a LangGraph workflow with human review, evals, and observability.
- **Out of scope; don't add them:** multi-tenancy and row-level security, database
  migrations, idempotency keys, message queues, rate-limit and quota billing, streaming
  and cancellation, any UI.
- **Per lesson:** build only what that lesson's SPEC.md lists. Code for a later lesson
  waits for that lesson, even when it would be easy now.

## Plan

Before writing code for anything bigger than a one-line fix:

1. Read the lesson's SPEC.md and the tests named in it.
2. Write the plan: the files you'll touch, the order (bottom-up: pure functions first),
   the test that proves each step, and the failure mode it adds or closes. `/plan-lesson
   NN` does this.
3. Ask about anything the spec leaves open. Record the answer under Clarifications.
4. Build one module at a time; run its tests after each; run `/verify` at the end.

## Commands

```bash
uv sync --all-groups              # install
uv run ruff check .               # lint (line length 100)
uv run pytest                  # all tests (fast, offline)
uv run underwriter run-all        # 8 sample applications vs expected outcomes
uv run underwriter eval           # golden cases + release gates (lesson 6 on)
uv run underwriter eval-retrieval # retrieval eval (lesson 2 on)
uv run underwriter run data/applications/APP-002.json   # one case, full trace
```

Everything runs offline on a deterministic mock LLM. Never require an API key for tests.

## Rules of this system (never break these)

1. **The agent proposes; the engine decides.** The LLM writes an `AgentRecommendation`.
   Only `decision/engine.py` turns facts into APPROVE / DECLINE / MANUAL_REVIEW. Never
   let model output, a tool result or retrieved text change a threshold or a decision.
2. **Escalate, never guess.** Missing or conflicting data becomes a reason code and
   MANUAL_REVIEW. Never invent a credit score, income or policy. Never default to 0.
3. **Typed results at every boundary.** External calls return a status (`OK`,
   `UNAVAILABLE`, `INVALID`) with a reason, never `None` and never a bare exception.
4. **Provider-agnostic.** Nothing outside `src/underwriter/llm/` imports a model SDK.
5. **Fault injection is a feature.** New external dependencies get a fault kind and a
   test. Faults are refused when `APP_ENV=production`.
6. **Everything is audited.** A step that runs, retries, degrades or fails leaves an
   `AuditEvent`. The audit is append-only.
7. **No personal data in prompts, messages or traces.** Names, national-ID digits,
   emails, dates of birth and addresses go only into evidence on the audit trail (lesson
   7). The application id (`APP-002`) is not personal data and may appear.

## How to work here

These follow the `karpathy-guidelines` skill, applied to this repo.

- **Think before coding.** State your assumptions. If the request is ambiguous, ask, or
  present the options. Asking is part of doing the job well.
- **Plan first** for anything bigger than a one-line fix: the files you'll touch, the
  tests that prove it, and the failure mode it adds (if any).
- **Simplicity first.** Write the code this lesson needs and nothing for later lessons.
  No new dependency without saying why.
- **Surgical changes.** Touch only what the task needs. Don't reformat unrelated code.
  Flag dead code you notice rather than deleting it.
- **Goal-driven.** Turn the task into a test that fails, make it pass, then run
  `/verify`. You're done when ruff, pytest, run-all and (from lesson 6) eval are green.

## Don't touch without being asked

- `tests/` and `evals/`. Make failing tests pass by fixing the code, not the tests.
- `decision/policy.py` thresholds. They are business commitments, not tuning knobs.
- Golden-case expectations in `evals/golden_cases.json`. Expected answers come from
  reading the policy or regulation, never from running the system.
- `data/corpus/`. These are real federal documents with checksums.

## Code map

| Area | Where | Lesson |
|---|---|---|
| Domain types, reason codes | `src/underwriter/domain/models.py` | 1 |
| Exact calculations | `src/underwriter/risk/calculations.py` | 1 |
| Policy thresholds, decision engine | `src/underwriter/decision/` | 1 |
| Service contracts and lesson 1 services | `src/underwriter/workflow/contracts.py`, `services.py` | 1 |
| Retrieval (parse, chunk, BM25, vectors, RRF) | `src/underwriter/rag/` | 2 |
| LLM port and mock | `src/underwriter/llm/` | 3 |
| Context, prompts, validation, agents | `src/underwriter/agents/` | 3–4 |
| Typed external checks, fault plans | `src/underwriter/tools/` | 4 |
| Workflow graph, node policies | `src/underwriter/workflow/graph.py`, `resilience.py` | 5 |
| Eval harness | `src/underwriter/evaluation/`, `evals/` | 6 |
| Tracing, usage metering | `src/underwriter/observability/`, `llm/instrumented.py` | 7 |
| Retries with full jitter, concurrent checks under a deadline | `src/underwriter/reliability/` | 8 |

Each lesson has `lessons/NN-*/README.md` (the guide), `SPEC.md` (what to build) and
`PROMPTS.md` (how to build it with you).

## Skills and commands

| When | Command | Skill(s) |
|---|---|---|
| Starting a lesson | `/start-lesson NN` | — |
| Something is unclear | `/clarify <task>` | `clarify-before-building` (Superpowers) |
| Before code | `/plan-lesson NN` | `clarify-before-building`, `write-plan` (Superpowers) |
| Writing a module | `/build-module <path>` | `tdd-module` (Superpowers), `karpathy-guidelines` |
| A test fails or a decision looks wrong | — | `debug-root-cause` (Superpowers) |
| Before saying "done" | `/verify` | `verify-before-done` (Superpowers) |
| Before the PR | `/review`, then `/learn <finding>` | `review-and-learn` (Superpowers) |
| Behind on a lesson | `/catch-up NN` | — |
| "Why was this decided?" | `/explain-decision APP-00N` | `investigate-decision` |
| Where did time and tokens go? (L7) | `/trace APP-00N` | — |
| Eval status (L6) | `/eval-report` | — |
| Use-case work | — | `add-policy-rule`, `add-tool-check`, `add-golden-case`, `add-sample-application`, `add-regulatory-document`, `add-retrieval-case`, `new-prompt-version`, `add-workflow-node` |

The procedures behind these are written out for people in `workflows/`. Third-party
sources and licences are in `.claude/skills/THIRD_PARTY_NOTICES.md`.

## Style

Python 3.11+, pydantic v2, type hints everywhere, `from __future__ import annotations`.
Docstrings explain *why*. Plain names. Tests are small, named for the behaviour, and
cover both sides of every threshold.

## Clarifications (questions the spec left open, and the answer that stands)

Add one line when you ask something and get an answer: the question, the answer, and
where it came from. Don't re-ask what's settled here.

- **0% interest:** monthly payment is principal / term. (Lesson 1; policy §4.)
- **Which income for DTI?** Verified *gross* monthly income, not stated and not net.
  (Policy §4–5.)
- **The agent proposes DECLINE and policy doesn't decline:** MANUAL_REVIEW. An agent may
  escalate; it may never decline on its own or relax policy. (ADR-0002.)
- **Required vs optional checks:** `credit_bureau` and `fraud_screen` are required (an
  outage escalates); `bank_data` and `employment_verification` are optional (an outage
  costs corroboration, not the decision). (Lesson 4.)
- **Policy retrieval down:** degrade and say so in the audit. The engine's thresholds
  never depended on retrieval. (Lesson 5; F8.)
- **"Today" for the corpus** is fixed at 2026-10-22 (`rag/retriever.py`), so in-force
  checks behave the same every year. (Lesson 2.)
- **Slow or flaky checks:** only timeouts, 429s and 500s are retried (full jitter, `Retry-After`
  as a floor, never past the deadline); a check still running at the 3 s checks deadline is
  UNAVAILABLE and the lesson 4 required/optional rules apply. (Lesson 8; F10.)
- **Prices in `observability/metering.py`** are placeholders. A real price needs the
  provider's own page and the date it was checked. (Lesson 7.)

## Learnings from PRs (add to this list; it's how the next session learns)

One line per lesson learned in review: what went wrong, and the rule that prevents it.

- Read `<case_json>` from the system prompt as well as the user message and parsed the
  wrong block. Read only what the code is meant to read.
- Named a pydantic field `json`, which shadows a BaseModel method. Check names.
- Patched a module constant in a test, but the function had bound it as a default
  argument at import, so nothing changed. Patch the instance or the call site.
- A degraded node's failure event was overwritten by its own success update. When you
  merge dict updates, merge lists rather than replacing them.
- Put an upstream error message ("no record for applicant ending 5562") and both names
  from an identity check into signal messages. Messages reach the LLM context and
  traces; names and ids belong only in evidence on the audit trail.
- Forgot that worker threads don't inherit context: spans lost their parent until
  `contextvars.copy_context().run` was used in `run_node`.
