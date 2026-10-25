---
description: Record what a review or a bug taught, as one line in CLAUDE.md › Learnings from PRs
argument-hint: "<the finding or mistake, in a few words>"
---
<task>Turn "$ARGUMENTS" into a learning for future sessions, using the review-and-learn
skill.</task>

<format>One line under "Learnings from PRs" in CLAUDE.md: what went wrong, concretely,
then the rule that prevents it. Written so a new session can follow it without this
conversation.</format>

<check>Read the existing lines first. If one already covers it, sharpen that line instead
of adding a near-duplicate.</check>

<output>Show the line you added or changed, and the diff of CLAUDE.md.</output>
