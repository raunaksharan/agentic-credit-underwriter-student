# Lesson 8 prompt pack: build retries with full jitter and concurrent checks with Claude Code

You build two modules in `src/underwriter/reliability/` from `SPEC.md`. The rest of the
system already calls them:
- `run_check` wraps each tool call in your `call_with_retry`;
- the orchestrator runs your `run_checks_concurrently`;
- `bench` compares it with the old sequential `run_checks`.

```bash
cd ~/fde-work/lesson-08        # your copy of starter/lesson-08 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: every file, until both modules exist
claude
```

```text
/start-lesson 08
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 08
```

The order is backoff first (pure functions, a fake clock, a seeded random source), then
the concurrent runner. Ask the plan to name the failure mode each step closes (F10 in
`architecture/failure-modes.md`).

Then scaffold the interfaces (5 min). `tools/checks.py` imports `backoff.py`, and the
orchestrator imports `parallel.py`, so nothing imports at all until both modules have
their names:

```text
<task>Scaffold the public API of lesson 08's modules</task>
<spec>lessons/08-reliability/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; dataclasses get their fields.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one rather than at import, and ruff is clean. No
logic yet.</done_when>
```

## 2. Backoff with full jitter (30 min)

```text
<task>Build src/underwriter/reliability/backoff.py: RETRYABLE, RetryPolicy, NO_RETRY,
backoff_ceiling, full_jitter, retry_delay, call_with_retry</task>
<spec>lessons/08-reliability/SPEC.md, section "reliability/backoff.py"</spec>
<tests>uv run pytest tests/test_reliability.py -k backoff</tests>
<constraints>Retry only RETRYABLE; "no record", malformed and bugs fail on the first
attempt. Retry-After is a floor. Never sleep past the deadline, and never after the last
attempt. Use the injected sleep, rng and clock only: no time.sleep or random module calls
in the logic.</constraints>
<done_when>Those tests pass and ruff is clean.</done_when>
```

Ask Claude: what would happen to a bureau that just recovered if 100 clients retried
after exactly 0.5 s? Then ask why `full_jitter` draws from 0 rather than from half the
ceiling.

## 3. Concurrent checks under one deadline (30 min)

```text
<task>Build src/underwriter/reliability/parallel.py: CHECKS_DEADLINE_S, MAX_WORKERS,
DEFAULT_RETRY, deadline_result, run_checks_concurrently</task>
<spec>lessons/08-reliability/SPEC.md, section "reliability/parallel.py"</spec>
<tests>uv run pytest tests/test_reliability.py -k parallel, then uv run pytest, then
uv run underwriter run-all</tests>
<constraints>Results in spec order, never finish order. One shared deadline; a check
that misses it becomes deadline_result, and you don't wait for it. Each task runs in
contextvars.copy_context(), so spans keep their parent; open no new span. Read the
module constants at call time.</constraints>
<done_when>The whole suite is green, run-all shows 8/8, and ruff is clean.</done_when>
```

Then measure, and read what happened:

```bash
uv run underwriter bench
uv run underwriter bench --tool-fault credit_bureau=flaky:2,bank_data=latency:3500
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=latency:3500
uv run underwriter eval                     # PASSED: 35/35 cases
```

Why does the slow bureau give MANUAL_REVIEW but the slow bank data still approve? Find
the rule. It's from lesson 4, not lesson 8.

## 4. Verify, review, learn (10 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest`, `run-all` (8/8) and `eval` (35/35) are green.
- `bench` shows the concurrent run near the slowest check, not the sum.
- Your PR answers: which failures do you retry, which never, and why does a check that
  misses the deadline become UNAVAILABLE rather than being waited for?

## Don't delegate

The deadline and the retry budget (`CHECKS_DEADLINE_S`, `DEFAULT_RETRY`). They trade
latency against how often a case goes to a human, which is a business decision. Write
down the numbers behind them (exercise 2).
