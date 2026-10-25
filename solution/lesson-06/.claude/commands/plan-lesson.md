---
description: Plan a lesson's build before writing any code (clarify, then a test-first plan)
argument-hint: "<lesson number, e.g. 03>"
---
<task>Plan lesson $ARGUMENTS. Don't write code yet.</task>

<read>
CLAUDE.md (Context, Scope, Plan, Clarifications, Learnings from PRs);
lessons/$ARGUMENTS-*/SPEC.md, PROMPTS.md and README.md; the tests SPEC.md names.
</read>

<steps>
1. Use the clarify-before-building skill. Ask me, one at a time, about anything the spec
   leaves open that would change the code, and record each answer under Clarifications.
2. Use the write-plan skill. Save the plan to docs/plans/lesson-$ARGUMENTS-<name>.md:
   goal, the tests that prove it, review focus (failure modes), and one task per module,
   bottom-up, each with the exact names from SPEC.md.
3. List what you will not touch: tests/, evals/, decision/policy.py, data/corpus/, and any
   module not in this lesson's SPEC.md.
</steps>

<stop>Show the plan and wait for me to approve or change it. If nobody can answer (an
unattended run), answer the open questions from SPEC.md, CLAUDE.md and the seed code, write
each answer as an assumption in the plan, and treat the plan as approved.</stop>
