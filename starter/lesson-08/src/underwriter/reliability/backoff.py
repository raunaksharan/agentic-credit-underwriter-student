"""Retry with exponential backoff and full jitter (lesson 8).

Why full jitter: when a dependency blips, every client that failed retries. With a fixed
delay (or plain exponential backoff) they all retry at the same instants and knock it
over again. Full jitter spreads each retry uniformly over [0, min(cap, base * 2^(n-1))],
so the retries arrive as a trickle instead of waves.

What is retried, and what isn't:
- timeouts, 429s and 500s are transient: the next attempt may succeed;
- "no record" and a malformed answer are not: asking again gets the same answer;
- a 429's Retry-After is a floor: never retry sooner than the server asked;
- never sleep past the deadline: if the next wait would cross it, give up now.

The clock, the sleep and the random source are injected, so tests are exact and fast.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/08-reliability/SPEC.md; the tests are the answer key.
"""
