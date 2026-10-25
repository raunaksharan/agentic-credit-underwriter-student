# Build a module with Claude Code

**When:** every module in a lesson's SPEC.md. This is the core loop of the course.

## Steps

| Step | You type | Claude uses | You check |
|---|---|---|---|
| 1. Clarify | `/clarify <the module>` (only if something's open) | `clarify-before-building` | Each answer is a line in CLAUDE.md › Clarifications |
| 2. Plan | `/plan-lesson NN` | `write-plan` | The plan in `docs/plans/` goes bottom-up and names the tests. Reject a plan that edits tests |
| 3. Build | `/build-module src/underwriter/<path>.py` | `tdd-module`, `karpathy-guidelines` | It ran the tests red first, then green. Read the diff |
| 4. Debug (if red) | describe the failure | `debug-root-cause` | It found a cause before changing code |
| 5. Verify | `/verify` | `verify-before-done` | The real numbers: tests, run-all, evals |
| 6. Review | `/review` | `review-and-learn` | Accept or reject each finding, with a reason |
| 7. Learn | `/learn <what went wrong>` | `review-and-learn` | One new line in CLAUDE.md › Learnings from PRs |
| 8. Explain back | (in your own words, in the PR) | — | You can say why it works without Claude |

A good build prompt has this shape (PROMPTS.md has one per module):

```text
<task>Build src/underwriter/rag/fusion.py</task>
<spec>lessons/02-rag/SPEC.md, section "fusion.py"</spec>
<tests>uv run pytest tests/test_rag_fusion.py -q</tests>
<constraints>No new dependency. Don't edit tests/. Only the names SPEC.md lists.</constraints>
<done_when>Those tests pass, the suite has no new failures, ruff is clean.</done_when>
```

## Don't delegate

- thresholds and golden answers;
- deciding which review findings are real;
- the explain-back paragraph.

## Done when

The lesson's tests are green, `/verify` is clean, and the PR has the plan, the rejected
findings with their reasons, the learning lines and your explanation.
