# Lesson 8 — Reliability & performance: fast when things work, safe when they don't

> A decision that waits forever on a slow bureau is as useless as a wrong one. Bound the
> wait, retry only what can succeed, and keep the decision rules exactly as they were.

**Slides:** to follow
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-08/` in the course repo

## Objectives

By the end of this lesson students can:

1. Say which failures are worth retrying (timeouts, 429s, 500s) and which aren't ("no
   record", a malformed answer, a bug), and why.
2. Implement exponential backoff with **full jitter**, honour `Retry-After`, and never
   sleep past a deadline.
3. Run independent checks concurrently, and explain why the total drops from the sum of
   the latencies to about the slowest one.
4. Bound a step with an overall deadline, and turn a check that misses it into a typed
   `UNAVAILABLE` result, so the existing rules escalate or degrade.
5. Keep results deterministic under concurrency (spec order), and keep trace context
   across threads.
6. Measure before and after (`underwriter bench`, the lesson 7 traces, the eval's p95
   gate).

## What changed since lesson 7

| | Lesson 7 | Lesson 8 |
|---|---|---|
| Checks | one after another | concurrent (4 workers), one 3 s deadline for the step |
| A slow check | the node's 10 s timeout fails the whole step | that check alone is `UNAVAILABLE` ("deadline of 3.0s exceeded"); the rules decide |
| Transient errors | one attempt | up to 3 attempts, full-jitter backoff, `Retry-After` as a floor |
| Faults | `latency:<ms>` and the error kinds | plus `flaky:<n>`: a 500 on the first n calls, then normal answers |
| CLI | `trace` | `bench`: sequential vs concurrent, same faults |
| Eval | 32 cases | 35: a bureau that recovers on retry, a bureau slower than the deadline, a slow optional check |

## Agenda

| Time | Block |
|---|---|
| 0:00 | What "reliable" means here: a bounded, explainable decision, not "never fails" |
| 0:10 | Transient vs permanent failures; why retrying "no record" is a bug |
| 0:20 | Backoff, and why jitter: the thundering herd |
| 0:35 | Concurrency for I/O-bound checks; threads, deadlines, cancellation |
| 0:50 | Determinism and context across threads (lesson 7's spans) |
| 1:05 | Measure: `bench`, traces, the eval's p95 gate |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: what would you do differently with a real bureau SLA? |

## Setup

```bash
cd solution/lesson-08          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run pytest                                   # 202 tests
uv run underwriter bench                        # sequential vs concurrent checks
uv run underwriter eval                         # PASSED: 35/35 cases
```

## Walkthrough

```bash
uv run underwriter bench
uv run underwriter bench --tool-fault credit_bureau=flaky:2,bank_data=latency:3500
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=flaky:1
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=latency:3500
uv run underwriter trace data/applications/APP-001.json --tool-fault credit_bureau=flaky:2
```

Things to point at:

1. **Sum vs max.** Four checks at 200 ms each: about 800 ms one after another, about 200
   ms concurrently. The checks are I/O-bound, so threads are enough.
2. **A flaky bureau recovers.** `credit_bureau=OK×3` in `bench`; `attempts` is on the
   check's audit event and span. The decision is the same as with no fault.
3. **A slow bureau is bounded.** With `latency:3500` the decision comes back after about
   3 s, as MANUAL_REVIEW with `CREDIT_DATA_UNAVAILABLE`. The rules didn't change: a
   required check that is UNAVAILABLE always escalated. Lesson 8 only made "slow" become
   "unavailable" on time.
4. **A slow optional check only costs corroboration.** `bank_data=latency:3500` still
   approves.
5. **Not everything is retried.** A malformed answer or "no record" fails on the first
   attempt: asking again gets the same answer, more slowly.
6. **Order is deterministic.** Results come back in spec order, however the threads
   finish, so audit trails and tests don't flake.
7. **The process can outlive the decision.** A worker that missed the deadline can't be
   killed in Python; it finishes in the background and its result is thrown away. In a
   service, the HTTP client's own timeout is what really frees it (exercise 2).

## Lab exercises

### Exercise 1: Why full jitter? (30 min)

Simulate 100 clients that all fail at t=0 and retry with (a) a fixed 0.5 s delay, (b)
exponential backoff without jitter, (c) full jitter. Count how many retries land in each
100 ms bucket over the first 3 seconds, and plot or print the three histograms. Which one
would you want hitting a bureau that just recovered? Write the answer in two sentences.

### Exercise 2: Choose the deadline from data (35 min)

Run `run-all` with `OTEL_EXPORTER=memory` (or `trace` on each sample) and collect the
`check …` span durations. Propose `CHECKS_DEADLINE_S` from the p95 or p99 of the slowest
required check, plus the retry budget. Then explain what a real HTTP client must do so a
timed-out call actually stops (connect and read timeouts below the deadline).

### Exercise 3: A circuit breaker (35 min)

If the bureau has failed on the last N calls, stop calling it for a cool-down period and
return `UNAVAILABLE` at once ("circuit open"). Add it around `run_check` for one tool,
with a fault test that shows the second case after an outage takes milliseconds, not the
full retry budget. Where does breaker state live, and what happens with several worker
processes?

## Homework / deliverable

PR containing:

- [ ] The jitter histograms and your two-sentence answer
- [ ] A deadline proposal with the numbers behind it
- [ ] The circuit breaker with its tests, or a written design if you ran out of time

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Retry scope | Only transient errors; `Retry-After` honoured; deadline respected | Retries everything, including bugs |
| Backoff | Full jitter, capped, injected clock and random source in tests | Fixed sleep; tests that sleep for real |
| Concurrency | Deterministic order; context carried into threads | Results in finish order; orphan spans |
| Deadline | A miss becomes a typed result the rules already handle | A hung step, or a silent default |
| Evidence | Before/after numbers from `bench` or traces | "It feels faster" |

## Interview questions this lesson prepares for

- Which errors do you retry, and which do you never retry? Why?
- What is full jitter, and what problem does it solve?
- How do you put a deadline on four parallel calls, and what happens to the slow one?
- A dependency is down. How do you stop every request paying its full timeout?
- How do you keep tests of retry logic fast and deterministic?

