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
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from underwriter.tools.faults import ToolRateLimited, ToolServerError, ToolTimeout

T = TypeVar("T")
RETRYABLE: tuple[type[Exception], ...] = (ToolTimeout, ToolRateLimited, ToolServerError)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_s: float = 0.1
    cap_s: float = 1.0


NO_RETRY = RetryPolicy(max_attempts=1)


def backoff_ceiling(attempt: int, policy: RetryPolicy) -> float:
    """The upper bound of the wait after failed attempt `attempt` (1-based)."""
    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt}")
    return min(policy.cap_s, policy.base_s * 2 ** (attempt - 1))


def full_jitter(attempt: int, policy: RetryPolicy, rng: random.Random) -> float:
    """A wait drawn uniformly from [0, backoff_ceiling(attempt, policy)]."""
    return rng.uniform(0, backoff_ceiling(attempt, policy))


def retry_delay(exc: Exception, attempt: int, policy: RetryPolicy,
                rng: random.Random) -> float:
    """Full jitter, but never sooner than a 429's Retry-After."""
    delay = full_jitter(attempt, policy, rng)
    if isinstance(exc, ToolRateLimited):
        delay = max(delay, exc.retry_after_s)
    return delay


def call_with_retry(fn: Callable[[], T], policy: RetryPolicy = NO_RETRY, *,
                    sleep: Callable[[float], None] = time.sleep,
                    rng: random.Random | None = None,
                    clock: Callable[[], float] = time.monotonic,
                    deadline: float | None = None) -> tuple[T, int]:
    """Call fn until it succeeds or the policy says stop. Returns (value, attempts).

    A non-retryable exception is raised at once. When the attempts run out, or the next
    wait would reach `deadline` (a `clock()` time), the last exception is raised.
    """
    rng = rng or random.Random()
    attempt = 1
    while True:
        try:
            return fn(), attempt
        except RETRYABLE as exc:
            if attempt >= policy.max_attempts:
                raise
            delay = retry_delay(exc, attempt, policy, rng)
            if deadline is not None and clock() + delay >= deadline:
                raise
            sleep(delay)
            attempt += 1
