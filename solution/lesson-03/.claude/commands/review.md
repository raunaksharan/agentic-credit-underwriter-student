---
description: Independent review of the current diff against this repo's rules
---
<task>Get an independent review of the current work, using the review-and-learn skill.</task>

<reviewer>
A subagent that has not seen this session. Give it CLAUDE.md,
architecture/failure-modes.md, the lesson's SPEC.md if there is one, and the output of
`git diff` (staged and unstaged). Without git, give it the lesson's student modules
(listed in SPEC.md) and any other file you changed.
</reviewer>

<check>
1. Breaks of the CLAUDE.md rules (agent proposes / engine decides, never guess, typed
   results, no SDK outside llm/, fault injection, audit, no personal data).
2. Edits to tests, evals, thresholds or golden-case expectations.
3. Missing tests: every new branch, and both sides of every threshold.
4. Code beyond what the spec asked for.
</check>

<output>Findings ranked by severity, each with file:line and why it matters. Don't fix
anything. Then wait: I'll decide which findings to act on, and /learn records the
lessons.</output>
