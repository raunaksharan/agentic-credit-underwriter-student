---
description: Run every check this repo has and report what passed, failed or was skipped
---
<task>Verify the repo, using the verify-before-done skill. Evidence, not claims.</task>

<checks>
Run these from the repo root, in order, and keep going after a failure:
1. uv run ruff check .
2. uv run pytest
3. uv run underwriter run-all
4. uv run underwriter eval-retrieval   (skip if the command doesn't exist yet)
5. uv run underwriter eval             (skip if the command doesn't exist yet)
</checks>

<report>
A short table: check · result (with counts) · the first failing line, if any.
If anything failed, name the file you think is responsible and why, but don't change code
until I say so. If everything passed, say so in one line with the numbers.
</report>
