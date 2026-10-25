---
description: Run the golden-case eval and summarize the gates and any regressions (lesson 6 on)
argument-hint: "[--tag <family>]"
---
<task>Run the eval $ARGUMENTS and report it.</task>

<run>uv run underwriter eval $ARGUMENTS --markdown /tmp/eval.md</run>

<report>
Pass or fail per gate, with the actual against the limit. List the failing cases, each
with its scenario sentence and the first failure line. Compare against evals/baseline.json
(tokens, pass rate). Never update the baseline unless I ask, and then say why each
metric moved.
</report>
