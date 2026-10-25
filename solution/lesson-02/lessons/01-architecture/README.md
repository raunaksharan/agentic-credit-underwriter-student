# Lesson 1 — Business Problem → Enterprise AI Architecture

> Before writing a prompt, decide where AI belongs, and where it must not.

**Slides:** [PDF](slides/lesson-01-architecture.pdf)
**Duration:** 3 hours (90 min concepts + walkthrough, 90 min lab)
**Code at end of lesson:** `solution/lesson-01/` in the course repo

## Objectives

By the end of this lesson students can:

1. Turn an observed business workflow into functional and non-functional requirements.
2. Classify each workflow step as AI, deterministic or human, and justify it.
3. Draw service boundaries as typed contracts that let AI and code be swapped.
4. Design for failure: name what happens when each dependency returns nothing.
5. Put a human in the loop deliberately, with machine-readable reasons.
6. Run and extend a deterministic baseline that later AI components must beat.

## Agenda

| Time | Block |
|---|---|
| 0:00 | The FDE's first week: from "we want AI" to a workflow map ([requirements.md](../../architecture/requirements.md)) |
| 0:25 | AI vs deterministic: the one-question test ([ADR-0001](../../architecture/adr/0001-hybrid-ai-deterministic.md)) |
| 0:45 | System architecture and service boundaries ([architecture/](../../architecture/README.md)) |
| 1:05 | The agent proposes, the engine decides ([ADR-0002](../../architecture/adr/0002-agent-proposes-engine-decides.md)) |
| 1:20 | Failure modes and escalation ([failure-modes.md](../../architecture/failure-modes.md), [ADR-0003](../../architecture/adr/0003-escalate-never-guess.md)) |
| 1:30 | Break |
| 1:40 | Live walkthrough of the code (below) |
| 2:00 | Lab: exercises 1–3 |
| 2:50 | Debrief |

## Setup

```bash
git clone <repo> && cd agentic-credit-underwriter
uv sync --all-groups
uv run pytest            # 50 tests, all green
uv run underwriter run-all
```

## Walkthrough

Run it first, then read it.

```bash
uv run underwriter run data/applications/APP-008.json
```

Things to point at:

1. **`domain/models.py`**: every boundary is a Pydantic type. `AgentRecommendation`
   is a *proposal*; `UnderwritingDecision` is the *decision*. Different types on purpose.
2. **`workflow/contracts.py`**: each protocol is tagged DETERMINISTIC / AI / HUMAN and
   with the lesson that implements it.
3. **`risk/calculations.py`**: the numbers an LLM must never estimate.
4. **`decision/engine.py`**: policy as code, and the reconciliation rule.
5. **`workflow/orchestrator.py`**: the architecture diagram as a sequence, with
   an audit event at every step.
6. **APP-003**: open `tools/bureau.py`. No record → exception → `None` → review.
   `credit_score` is absent from the metrics. Absence is tested.
7. **APP-008**: the stub agent approves at 43.9% DTI; the engine overrides.

## Lab exercises

### Exercise 1: Classify the workflow (worksheet, 20 min)

For each of the 7 steps in [requirements.md](../../architecture/requirements.md#current-workflow-as-observed),
fill in:

| Step | AI / deterministic / human | Why | What if it fails? |
|---|---|---|---|

Then find **one step where reasonable people could disagree** and argue both sides.

### Exercise 2: Add a policy rule end to end (code, 40 min)

Policy §2.1: applicants must be at least 21 on the application date.

1. Add `UNDERAGE_APPLICANT` to `ReasonCode`.
2. Add `min_applicant_age` to `PolicyThresholds`.
3. Compute `applicant_age_years` in an analyzer (which one, and why?).
4. Decline in `DecisionEngine.evaluate_policy`, citing section 2.1.
5. Add a boundary test (20 vs 21) in `tests/test_decision_engine.py`.
6. Add sample case `APP-009` in `scripts/generate_sample_data.py`, regenerate,
   and make `run-all` pass.

**Acceptance:** `uv run pytest` green, `run-all` shows 9/9.

### Exercise 3: Write ADR-0004 (30 min)

Choose one:

- Should the decision engine allow an LLM to read the policy thresholds from the
  retrieved policy text instead of `policy.py`? Argue for and against; decide.
- Should a fraud signal ever auto-decline? Policy §8.2 says no. When might the
  business push back, and what would you build instead?

Use the format of the existing ADRs: Context, Decision, Consequences.

## Homework / deliverable

Submit a PR containing:

- [ ] Exercise 2 implemented with tests
- [ ] Your ADR-0004
- [ ] One new row in `failure-modes.md` for a failure we haven't covered, with a sample case if possible

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| AI vs deterministic reasoning | Justified by exactness, auditability and failure impact | "LLMs are good at this" |
| Boundaries | New logic lives behind an existing contract | Logic leaks into the orchestrator |
| Failure handling | Explicit reason codes; nothing guessed | Defaults or silent fallbacks |
| Tests | Boundary values on both sides of every threshold | Happy path only |
| Writing | ADR a new engineer could act on | Restates the code |

