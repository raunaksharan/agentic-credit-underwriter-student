---
description: Build one module from the lesson's SPEC.md, test-first, then verify
argument-hint: "<path, e.g. src/underwriter/rag/fusion.py>"
---
<task>Build $ARGUMENTS.</task>

<spec>The section for $ARGUMENTS in the current lesson's SPEC.md (lessons/NN-*/SPEC.md):
purpose, public API (exact names and signatures), behaviour, exact messages.</spec>

<method>Use the tdd-module skill and follow the karpathy-guidelines skill. Run the
module's tests and watch them fail, write the smallest code that satisfies the spec, then
run the whole suite. Keep the module docstring, extended to explain why.</method>

<constraints>
- Don't edit tests/, evals/, decision/policy.py or data/.
- Only the names the spec lists are public; nothing for a later lesson.
- If the spec is unclear, stop and ask (clarify-before-building); record the answer.
</constraints>

<done_when>The module's tests pass, the suite has no new failures, and ruff is clean.
Then show me the diff summary and suggest /verify.</done_when>
