"""Run the external checks concurrently, under one deadline (lesson 8).

Sequentially, four checks cost the sum of their latencies; concurrently, about the
slowest one. The deadline bounds that too: a check still running when it passes is
recorded as UNAVAILABLE ("deadline of 3.0s exceeded"), so a hung bureau sends the case
to a human instead of hanging the decision. The decision rules don't change: a required
check that is UNAVAILABLE escalates, an optional one costs corroboration.

Each check runs in a worker thread inside a copy of the caller's context, so its span
nests under the `checks` node span (lesson 7), and the run's settings (deadline, timed
out, retried) are added to that span. Results keep the order of the specs,
whatever order the threads finish in, so audit trails and tests are deterministic.

A worker that misses the deadline can't be killed; its result is thrown away.
"""

from __future__ import annotations

import contextvars
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait

from underwriter.domain.models import CheckResult, CheckStatus, LoanApplication
from underwriter.reliability.backoff import RetryPolicy
from underwriter.tools.checks import CHECKS, CheckSpec, run_check
from underwriter.tools.faults import FaultPlan

CHECKS_DEADLINE_S = 3.0
MAX_WORKERS = 4
DEFAULT_RETRY = RetryPolicy(max_attempts=3, base_s=0.1, cap_s=1.0)


def deadline_result(spec: CheckSpec, deadline_s: float) -> CheckResult:
    return CheckResult(tool=spec.name, required=spec.required,
                       status=CheckStatus.UNAVAILABLE,
                       reason=f"deadline of {deadline_s:.1f}s exceeded",
                       latency_ms=round(deadline_s * 1000, 2))


def run_checks_concurrently(app: LoanApplication, faults: FaultPlan | None = None,
                            specs: list[CheckSpec] | None = None, *,
                            deadline_s: float | None = None,
                            retry: RetryPolicy | None = None,
                            max_workers: int | None = None,
                            sleep: Callable[[float], None] = time.sleep,
                            rng: random.Random | None = None,
                            clock: Callable[[], float] = time.monotonic) -> list[CheckResult]:
    """Every check at once, each with retries, all within one deadline."""
    from opentelemetry import trace

    from underwriter.observability.tracing import set_attrs

    specs = specs or CHECKS
    faults = faults or FaultPlan()
    deadline_s = CHECKS_DEADLINE_S if deadline_s is None else deadline_s
    retry = retry or DEFAULT_RETRY
    workers = max_workers or MAX_WORKERS
    deadline = clock() + deadline_s
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="check")
    try:
        futures = [
            pool.submit(contextvars.copy_context().run, run_check, spec, app, faults,
                        retry=retry, deadline=deadline, sleep=sleep, rng=rng, clock=clock)
            for spec in specs]
        wait(futures, timeout=max(0.0, deadline - clock()))
        results = [f.result() if f.done() else deadline_result(spec, deadline_s)
                   for f, spec in zip(futures, specs, strict=True)]
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    set_attrs(trace.get_current_span(), checks__deadline_s=deadline_s,
              checks__timed_out=[r.tool for r in results
                                 if r.reason.startswith("deadline of")] or None,
              checks__retried=[r.tool for r in results if r.attempts > 1] or None)
    return results
