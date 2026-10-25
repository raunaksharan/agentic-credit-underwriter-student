---
description: Start a lesson in your own copy of its starter: what to build, what's red, where to begin
argument-hint: "<lesson number, e.g. 03>"
---
<task>Get me started on lesson $ARGUMENTS.</task>

<check_folder>This folder should be my copy of `starter/lesson-$ARGUMENTS` from the course
repo (START-HERE.md, step 2), not the course repo itself. If `src/` isn't here, tell me
to copy the starter first, and stop.</check_folder>

<steps>
1. Read lessons/$ARGUMENTS-*/SPEC.md and PROMPTS.md.
2. Run `uv sync --all-groups`, then `uv run pytest --continue-on-collection-errors`.
   Summarize what's red and why (missing modules, NotImplemented, import errors).
3. List the modules I'll build, in the order PROMPTS.md gives, with the test file for each.
</steps>

<next>Suggest `/plan-lesson $ARGUMENTS` as the next step. Don't write code.</next>
