---
description: Explain why one application was approved, declined or escalated, from what the system recorded
argument-hint: "<application id or path, e.g. APP-002>"
---
<task>Explain the decision for $ARGUMENTS, using the investigate-decision skill.</task>

<run>uv run underwriter run data/applications/<id>.json (add --json for the engine
findings; add the same --llm-fault / --tool-fault / --node-fault if I mention one)</run>

<answer>Three parts: the decision; the facts and rules that produced it, each with its
policy section; and what a human reviewer must look at if it escalated. Refer to the
application id only, never the applicant's name or details.</answer>
