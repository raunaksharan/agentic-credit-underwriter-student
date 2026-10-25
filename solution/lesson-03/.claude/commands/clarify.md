---
description: Ask the open questions about a task, one at a time, and record the answers in CLAUDE.md
argument-hint: "<what you're about to build or change>"
---
<task>Before building "$ARGUMENTS", find out what's open, using the
clarify-before-building skill.</task>

<read>CLAUDE.md › Clarifications first; then the relevant SPEC.md, policy section, ADRs
and failure modes.</read>

<output>One question per message, saying what the answer changes. After each answer, add
one line under Clarifications in CLAUDE.md. When nothing material is open, say what you
understood in three lines or fewer.</output>
