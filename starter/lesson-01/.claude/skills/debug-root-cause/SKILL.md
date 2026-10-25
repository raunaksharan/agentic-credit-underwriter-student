---
name: debug-root-cause
description: Use on any failing test, wrong decision, unexpected escalation or error in this repo, before proposing a fix. Finds the root cause from the error, the audit trail and the trace. Adapted from obra/superpowers systematic-debugging (MIT).
---

# Find the root cause before fixing anything

A symptom fix is a failure. (Adapted from obra/superpowers `systematic-debugging`; see
THIRD_PARTY_NOTICES.md.)

## 1. Investigate

- **Read the whole error,** including the test name and the first line of the
  traceback that is our code.
- **Reproduce it** with the smallest command: one test (`-k name`), or one case
  (`uv run underwriter run data/applications/APP-00N.json`, plus any `--llm-fault`,
  `--tool-fault` or `--node-fault`).
- **Look at what this system records:** the decision's reason codes and audit trail
  (`run` prints them); from lesson 7, `uv run underwriter trace <app>`, which shows
  which span failed, the attempts, and the time.
- **Check what changed:** `git diff`, `git log -3`.

## 2. Compare

Find the working example: a passing sample, the reference behaviour in SPEC.md, or the
finished code in the course repo's `solution/lesson-NN/` (diff your file against it).

## 3. One hypothesis at a time

State it ("the bureau INVALID result isn't mapped to CREDIT_DATA_UNAVAILABLE"), test it
with the smallest change or print, and confirm or drop it before the next one.

## 4. Fix, then prove it

Write or name the test that reproduces the bug (`tdd-module`), fix the cause, then run
`verify-before-done`. If the bug taught something general, use `review-and-learn` to add
it to CLAUDE.md › Learnings from PRs.

<rules>
- Three failed fixes in a row: stop, and question the assumption, not the code.
- Never "fix" by loosening a threshold, an expectation or a test.
</rules>
