"""External checks: fake tools behind one wrapper that never returns None.

    run_check(spec, app, faults) -> CheckResult(OK | UNAVAILABLE | INVALID, reason)

Each fake reads the synthetic data in data/ the way a real integration would read
an API. Lesson 8 runs these concurrently under a deadline and adds retries; the
contract (a typed result per check) stays the same.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/04-tool-agents/SPEC.md; the tests are the answer key.
"""
