"""Wrap any LLMClient with a span and a meter entry per call (lesson 7).

The wrapper is itself an LLMClient, so nothing else changes. Attribute names follow
the OpenTelemetry GenAI semantic conventions (gen_ai.*), so tracing backends that
understand them can chart tokens and latency per model without custom setup.
Prompts and replies are NOT recorded: they contain case data.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/07-observability/SPEC.md; the tests are the answer key.
"""
