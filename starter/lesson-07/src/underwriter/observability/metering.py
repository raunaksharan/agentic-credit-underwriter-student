"""Per-decision usage metering (lesson 7): tokens, model calls, cost, time per step.

Every LLM call reports into the meter of the decision being made. The meter lives
in a context variable, so concurrent decisions never mix their numbers, and it is
copied into worker threads with the rest of the context (see workflow/resilience.py).

Prices are a table in code, per million tokens, in USD. They are placeholders for
the class: check your provider's current price list and put the real numbers in
PRICES, or set LLM_PRICE_IN / LLM_PRICE_OUT for the model you use.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/07-observability/SPEC.md; the tests are the answer key.
"""
