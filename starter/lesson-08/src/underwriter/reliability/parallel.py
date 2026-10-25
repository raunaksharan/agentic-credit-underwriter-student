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

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/08-reliability/SPEC.md; the tests are the answer key.
"""
