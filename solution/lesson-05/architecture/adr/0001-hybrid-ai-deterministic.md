# ADR-0001: Hybrid system — AI only where it earns its place

**Status:** Accepted · Lesson 1

## Context

It is tempting to hand the whole application to one LLM prompt: "here are the
documents and the policy, should we lend?" That is fast to demo and impossible
to defend. Numbers drift, thresholds get paraphrased, failures are silent, and
nobody can explain a decision six months later.

## Decision

Classify every step of the workflow with one question: **does this step need
interpretation or judgement, or does it need to be exactly right every time?**

| Needs interpretation → AI | Needs exactness → deterministic code |
|---|---|
| Reading messy documents | DTI, payments, ratios |
| Finding relevant policy prose | Applying numeric thresholds |
| Weighing evidence, writing rationale | Validation and identity matching |
| Choosing which tool to call next | Recording the audit trail |

AI components sit behind the same typed contracts as deterministic ones
(`workflow/contracts.py`), so either can be swapped or tested in isolation.

## Consequences

- Most of the system is ordinary, testable code. The AI surface is small and
  deliberate, which makes evaluation (lesson 6) tractable.
- The workflow runs end to end with no LLM at all (lesson 1), giving a baseline
  every AI component must beat.
- Some flexibility is lost: a new policy rule needs a code change and a test,
  not a prompt edit. That is intended.
