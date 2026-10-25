---
description: Show where the time, tokens and failures went for one application (lesson 7 on)
argument-hint: "<application id, plus any --llm-fault/--tool-fault/--node-fault>"
---
<task>Trace $ARGUMENTS.</task>

<run>uv run underwriter trace data/applications/<id>.json <any faults given></run>

<report>The slowest spans and what they were doing, any ✗ spans and their errors, retries
(attempts), LLM calls with their tokens, and time no step owns. If `trace` doesn't exist
yet, say it arrives in lesson 7.</report>
