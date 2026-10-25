# Lesson 8 spec: retries with full jitter, concurrent checks under a deadline

**You build:**
- `src/underwriter/reliability/backoff.py`
- `src/underwriter/reliability/parallel.py`

**Given (the seed):** the Lesson 7 reference code, plus:
- `reliability/__init__.py`;
- the `flaky:<n>` fault kind in `tools/faults.py`;
- `tools/checks.py`, whose `run_check` already takes `retry`, `deadline`, `sleep`, `rng`
  and `clock` and calls your `call_with_retry` around each tool call;
- the orchestrator, which calls your `run_checks_concurrently`;
- the `bench` CLI command;
- three new golden cases (`G-R01`–`G-R03`) and the updated baseline.

**Answer key:** `tests/test_reliability.py`, the whole suite, `run-all` (8/8) and `eval`
(35/35).

```bash
uv run pytest tests/test_reliability.py -k backoff      # backoff.py (and the seeded retry in run_check)
uv run pytest tests/test_reliability.py -k parallel     # parallel.py
uv run pytest                     # everything, once parallel.py works
uv run underwriter bench
```

`tools/checks.py` imports `backoff.py`, and the orchestrator imports `parallel.py`, so
every test file errors at import until both modules exist. Scaffold first (PROMPTS
step 1).

## `reliability/backoff.py`: what to retry, and how long to wait

**Constants and types:**

- `T = TypeVar("T")`, for `call_with_retry`'s return type.
- `RETRYABLE = (ToolTimeout, ToolRateLimited, ToolServerError)` (from `tools/faults.py`).
  Nothing else is retried: `ToolNoRecord`, `ToolMalformed` and any other exception are
  raised on the first attempt.
- `RetryPolicy`, a frozen dataclass: `max_attempts: int = 3`, `base_s: float = 0.1`,
  `cap_s: float = 1.0`.
- `NO_RETRY = RetryPolicy(max_attempts=1)`.

**Functions:**

- `backoff_ceiling(attempt, policy) -> float`: `min(policy.cap_s, policy.base_s * 2 ** (attempt - 1))`.
  `attempt` is the number of the attempt that just failed, from 1. Below 1 raises
  `ValueError(f"attempt must be >= 1, got {attempt}")`.
- `full_jitter(attempt, policy, rng: random.Random) -> float`:
  `rng.uniform(0, backoff_ceiling(attempt, policy))`. It uses only the given `rng`, so a
  seeded `Random` repeats exactly.
- `retry_delay(exc, attempt, policy, rng) -> float`: `full_jitter(...)`, except that for
  a `ToolRateLimited` it is `max(jitter, exc.retry_after_s)`. The server's `Retry-After`
  is a floor.
- `call_with_retry(fn, policy=NO_RETRY, *, sleep=time.sleep, rng=None, clock=time.monotonic, deadline=None) -> tuple[T, int]`
  returns `(fn(), attempts)` on the first success. `rng` defaults to a new
  `random.Random()`. After a `RETRYABLE` exception on attempt `n`:
  1. if `n >= policy.max_attempts`, re-raise it;
  2. `delay = retry_delay(exc, n, policy, rng)`;
  3. if `deadline` is not `None` and `clock() + delay >= deadline`, re-raise it (there
     isn't time to wait and try again);
  4. `sleep(delay)`, then try attempt `n + 1`.

  A non-retryable exception propagates at once, with no sleep. `sleep` is called only
  between attempts, never after the last one.

## `reliability/parallel.py`: all checks at once, inside one deadline

**Constants:** `CHECKS_DEADLINE_S = 3.0`, `MAX_WORKERS = 4`,
`DEFAULT_RETRY = RetryPolicy(max_attempts=3, base_s=0.1, cap_s=1.0)`. Read them at call
time, not as default arguments: tests patch `parallel.CHECKS_DEADLINE_S`.

**`deadline_result(spec, deadline_s) -> CheckResult`** returns
`CheckResult(tool=spec.name, required=spec.required, status=UNAVAILABLE, reason=f"deadline of {deadline_s:.1f}s exceeded", latency_ms=round(deadline_s * 1000, 2))`.

**`run_checks_concurrently(app, faults=None, specs=None, *, deadline_s=None, retry=None, max_workers=None, sleep=time.sleep, rng=None, clock=time.monotonic) -> list[CheckResult]`:**

1. **Defaults.** `specs or CHECKS`, `faults or FaultPlan()`. `deadline_s` defaults to
   `CHECKS_DEADLINE_S`, `retry` to `DEFAULT_RETRY`, and `max_workers` to `MAX_WORKERS`.
2. **Deadline.** `deadline = clock() + deadline_s`, an absolute `clock()` time that every
   check shares.
3. **Submit.** Open a `ThreadPoolExecutor(max_workers=…)`. Submit one task per spec:
   `contextvars.copy_context().run(run_check, spec, app, faults, retry=retry, deadline=deadline, sleep=sleep, rng=rng, clock=clock)`.
   The copied context is what keeps each check's span under the `checks` node span
   (lesson 7).
4. **Wait.** `concurrent.futures.wait(futures, timeout=max(0, deadline - clock()))`.
5. **Collect.** For each spec, in spec order (never in finish order): the future's result
   if it is done, otherwise `deadline_result(spec, deadline_s)`. `run_check` turns every
   `ToolError` into a typed result, so a future only raises on a bug. Let that
   propagate: the `checks` node fails and its policy escalates (`WORKFLOW_ERROR`). Never
   swallow it.
   A seeded `rng` is shared by the worker threads, so draws interleave by timing. Tests
   that need exact delays call `call_with_retry` or `run_check` directly.
6. **Shut down.** `pool.shutdown(wait=False, cancel_futures=True)`, in `finally`. Don't
   wait for workers that missed the deadline; their results are thrown away.
7. **Trace.** Add these attributes to the current span
   (`opentelemetry.trace.get_current_span()`) with `set_attrs`:
   - `checks.deadline_s`;
   - `checks.timed_out`, the tools whose result is a `deadline_result` (`reason` starts
     `deadline of`), or `None` if none;
   - `checks.retried`, the tools with `attempts > 1` (`None` if none).

   Don't open a new span. The check spans must stay direct children of `node checks`.
8. Return the results.

The decision rules don't change. A required check that is UNAVAILABLE still escalates
(`CREDIT_DATA_UNAVAILABLE` or `CHECK_UNAVAILABLE`), and an optional one still costs only
corroboration. Lesson 8 only makes "slow" become "unavailable" on time.

## Changes to earlier modules

None of yours. These are the seed's changes to earlier modules, and they touch behaviour
earlier lessons stated:
- `run_check` gains keyword arguments, but with the defaults it behaves exactly as
  before (one attempt).
- The orchestrator's checks are now concurrent. Lesson 7's span test still holds, because
  check spans stay under `node checks`.
- `G-T02` (bureau 429) now waits about 2 s, because the retry honours `Retry-After: 2`
  before giving up at the deadline.

<!-- api:start -->

## Public API

### `src/underwriter/reliability/backoff.py`

Imported elsewhere (keep these names exactly): `NO_RETRY`, `RETRYABLE`, `RetryPolicy`, `backoff_ceiling`, `call_with_retry`, `full_jitter`, `retry_delay`

Builds on: `underwriter.tools.faults`

- constant `T = TypeVar('T')`
- constant `RETRYABLE = (ToolTimeout, ToolRateLimited, ToolServerError)`
- class `RetryPolicy`
  - field `max_attempts: int = 3`
  - field `base_s: float = 0.1`
  - field `cap_s: float = 1.0`
- constant `NO_RETRY = RetryPolicy(max_attempts=1)`
- function `backoff_ceiling(attempt: int, policy: RetryPolicy) -> float`
  > The upper bound of the wait after failed attempt `attempt` (1-based).
- function `full_jitter(attempt: int, policy: RetryPolicy, rng: random.Random) -> float`
  > A wait drawn uniformly from [0, backoff_ceiling(attempt, policy)].
- function `retry_delay(exc: Exception, attempt: int, policy: RetryPolicy, rng: random.Random) -> float`
  > Full jitter, but never sooner than a 429's Retry-After.
- function `call_with_retry(fn: Callable[[], T], policy: RetryPolicy=NO_RETRY, *, sleep: Callable[[float], None]=time.sleep, rng: random.Random | None=None, clock: Callable[[], float]=time.monotonic, deadline: float | None=None) -> tuple[T, int]`
  > Call fn until it succeeds or the policy says stop. Returns (value, attempts).
  >
  > A non-retryable exception is raised at once. When the attempts run out, or the next
  > wait would reach `deadline` (a `clock()` time), the last exception is raised.

### `src/underwriter/reliability/parallel.py`

Imported elsewhere (keep these names exactly): `CHECKS_DEADLINE_S`, `run_checks_concurrently`

Builds on: `underwriter.domain.models`, `underwriter.reliability.backoff`, `underwriter.tools.checks`, `underwriter.tools.faults`

- constant `CHECKS_DEADLINE_S = 3.0`
- constant `MAX_WORKERS = 4`
- constant `DEFAULT_RETRY = RetryPolicy(max_attempts=3, base_s=0.1, cap_s=1.0)`
- function `deadline_result(spec: CheckSpec, deadline_s: float) -> CheckResult`
- function `run_checks_concurrently(app: LoanApplication, faults: FaultPlan | None=None, specs: list[CheckSpec] | None=None, *, deadline_s: float | None=None, retry: RetryPolicy | None=None, max_workers: int | None=None, sleep: Callable[[float], None]=time.sleep, rng: random.Random | None=None, clock: Callable[[], float]=time.monotonic) -> list[CheckResult]`
  > Every check at once, each with retries, all within one deadline.

<!-- api:end -->
