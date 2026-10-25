"""Structured output and semantic validation.

A JSON object that parses is not the same as an answer you can use. Schema checks
catch shape; these checks catch content:

- every cited id exists in the context the model was given
- every number in "figures" equals the fact it claims to copy
- every percentage written in the rationale matches a known ratio
- missing information or open review signals cannot come with an APPROVE

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/03-structured-reasoning/SPEC.md; the tests are the answer key.
"""
