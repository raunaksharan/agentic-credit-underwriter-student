---
name: write-plan
description: Use when a lesson module, rule, check or change is clear enough to build, before touching code. Writes a small test-first plan in docs/plans/ from the lesson's SPEC.md. Adapted from obra/superpowers writing-plans (MIT).
---

# Write the plan

Write the plan for an engineer who hasn't seen this repo. They can write idiomatic
Python once they know the exact names, the exact tests and the order. What they can't
know is what you decided, so write that down. (Adapted from obra/superpowers
`writing-plans`; see THIRD_PARTY_NOTICES.md.)

**Save to:** `docs/plans/lesson-NN-<short-name>.md` (or `docs/plans/<date>-<change>.md`
outside a lesson). Commit it with the work.

## Header

```markdown
# <What this builds> plan

**Goal:** one sentence.
**Spec:** lessons/NN-*/SPEC.md (and the policy section, if any)
**Tests that prove it:** the files and test names from the spec
**Constraints:** CLAUDE.md rules that apply; files not to touch (tests/, evals/,
decision/policy.py, data/corpus/)

## Review focus
The two or three failure modes from architecture/failure-modes.md this work touches,
and the behaviour a credit officer would expect for each.
```

## Tasks

Bottom-up: pure functions first, then the code that calls them. One task per module, or
per function when a module is big. Each task:

```markdown
### Task N: <module or function>
**Files:** create or modify `src/underwriter/...`; tests `tests/test_...py`
**Interfaces:** consumes <exact names from earlier tasks or the seed>; produces
<exact names and signatures from SPEC.md that later code imports>
- [ ] Run the named tests and watch them fail (or error at import).
- [ ] Implement the smallest code that satisfies the spec.
- [ ] Run the tests; then the whole suite.
- [ ] ruff clean; commit with a message that says why.
```

Then stop and show the plan. Build only after it's approved.

<rules>
- Names and signatures come from SPEC.md exactly; the seed and the tests import them.
- No task for a later lesson's feature (karpathy-guidelines §2).
- If the spec covers several independent pieces, say so and plan them separately.
</rules>
