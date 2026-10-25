# Lesson 3 — Prompt & Context Engineering: an LLM that can be checked

> A JSON object that parses is not an answer you can use. Check the content, not just
> the shape.

**Slides:** [PDF](slides/lesson-03-structured-reasoning.pdf)
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-03/` in the course repo

## Objectives

By the end of this lesson students can:

1. Put every model provider behind one small port (`LLMClient`) and run everything offline on a deterministic mock.
2. Engineer the context: minimise personal data, give every fact an id, prioritise within a budget.
3. Ask for structured output against a strict schema and parse model replies robustly.
4. Write semantic validators: citations exist, numbers match the facts, recommendations are consistent with signals.
5. Repair once with targeted feedback, then fail safe to a human with a machine-readable reason.
6. Record model, prompt version, attempts and tokens with every proposal.

## What changed since lesson 2

| | Lesson 2 | Lesson 3 |
|---|---|---|
| Underwriting agent | `RulesUnderwritingAgent` (stub) | `LLMUnderwritingAgent` over `LLMClient` |
| Default model | — | `MockLLM` (deterministic, offline) |
| Real providers | — | `LLM_MODE=live LLM_MODEL=…` via LiteLLM (optional extra) |
| Output | Python object | JSON schema `UnderwritingOutput`, validated |
| Model failure | not possible | `INVALID_MODEL_OUTPUT` / `MODEL_UNAVAILABLE` → manual review |

The workflow, the decision engine and every lesson 1–2 test are untouched: the LLM agent implements the same `UnderwritingAgent` contract.

## Agenda

| Time | Block |
|---|---|
| 0:00 | The port: why nothing outside `llm/` imports a vendor SDK |
| 0:15 | Context engineering: minimise, cite, prioritise (`agents/context.py`) |
| 0:35 | The prompt: instruction hierarchy and one worked example (`agents/prompts/underwriting_v1.md`) |
| 0:50 | Structured output and semantic validation (`agents/validation.py`) |
| 1:05 | Repair once, then fail safe (`agents/underwriting.py`) |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: what the validators can and can't catch |

## Setup

```bash
cd solution/lesson-03          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run underwriter check-llm      # mock: no key needed
uv run pytest                     # 104 tests
```

Optional, with your own key:

```bash
uv sync --all-groups --extra llm
export LLM_MODE=live LLM_MODEL=<a model your provider offers>   # e.g. gpt-4o-mini, gemini/…, anthropic/…
export OPENAI_API_KEY=…   # or GEMINI_API_KEY / ANTHROPIC_API_KEY / AZURE_API_KEY
uv run underwriter check-llm
uv run underwriter run-all
```

Quotas and prices change; check your provider's current limits before class, and keep the class on mock mode by default.

## Walkthrough

```bash
uv run underwriter prompt data/applications/APP-006.json          # exactly what the model sees
uv run underwriter run data/applications/APP-002.json             # valid on the first attempt
uv run underwriter run data/applications/APP-002.json --llm-fault malformed          # repaired
uv run underwriter run data/applications/APP-002.json --llm-fault wrong_number_always # human
uv run underwriter run data/applications/APP-001.json --llm-fault unavailable        # human
uv run underwriter run data/applications/APP-005.json --llm-fault malformed_always   # still DECLINE
```

Things to point at:

1. **`prompt` output**: there is no name, date of birth, ID or address in it. Every fact has an id (`metric:post_loan_dti`, `signal:IDENTITY_MISMATCH`, `mdl-upl-policy-3.2#8`).
2. **The prompt** tells the model it *proposes*; the engine decides. That instruction is a courtesy, and the architecture doesn't depend on the model obeying it (lesson 1, ADR-0002).
3. **`figures`**: we make the model copy the numbers it relies on, then compare them with the facts. "It said 35.6% but the fact is 45.6%" is a precise repair message.
4. **The repair loop** sends the model its own answer plus the exact errors, once. Unlimited retries just spend tokens.
5. **Fail safe**: an invalid or missing proposal becomes `MANUAL_REVIEW` with `INVALID_MODEL_OUTPUT` or `MODEL_UNAVAILABLE`. A clear policy decline (APP-005) still stands, because it never depended on the model.

## Lab exercises

### Exercise 1: Write one new semantic validator (35 min)

Add a check to `semantic_errors`: if the model recommends `DECLINE`, at least one cited id must be a policy chunk (an adverse action must point at a rule). Add a failing case to `tests/test_llm_agent.py` first, then make it pass.

### Exercise 2: Context budget (30 min)

Run `underwriter prompt` for APP-006 with `MAX_CONTEXT_CHARS` at 6000, 3000 and 2000. What is dropped first, and is that the right order? Propose and implement one change to the priority order, and defend it in two sentences.

### Exercise 3: Prompt version 2 (35 min)

Copy the prompt to `underwriting_v2.md` and make one deliberate change (for example, require a one-line summary of compensating factors). Bump `PROMPT_VERSION`, run the suite on mock, and if you have a key, run `run-all` live with both versions. Write down what changed in the proposals.

## Homework / deliverable

PR containing:

- [ ] The DECLINE-needs-a-policy-citation validator, with its test
- [ ] Your context-priority change with the two-sentence defence
- [ ] Prompt v2 plus a short note comparing v1 and v2 (mock or live)

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Validators | Check content against the facts given | Check only that fields exist |
| Repair | One retry with the specific errors | Retry until it works |
| Failure | Typed reason, human review, policy still applies | Exception or silent default |
| Context | Minimal, cited, budgeted | "Send the whole application" |
| Provenance | Model, prompt version, tokens recorded | Can't tell which prompt made a decision |

## Interview questions this lesson prepares for

- How do you validate LLM output beyond JSON schema?
- How do you keep PII out of prompts, and why does it matter beyond privacy?
- What do you do when the model provider is down or over quota?
- How do you version prompts and know which one produced a decision?
- Retry policy for malformed output: how many attempts, and with what feedback?

