"""Lesson 8: retries with full jitter, concurrent checks under one deadline."""

from __future__ import annotations

import random
import time

import pytest

from underwriter.domain.models import CheckStatus, ReasonCode, Recommendation
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.reliability import parallel
from underwriter.reliability.backoff import (
    NO_RETRY,
    RETRYABLE,
    RetryPolicy,
    backoff_ceiling,
    call_with_retry,
    full_jitter,
    retry_delay,
)
from underwriter.reliability.parallel import run_checks_concurrently
from underwriter.tools.checks import CHECKS, run_check, run_checks
from underwriter.tools.faults import (
    FaultPlan,
    ToolMalformed,
    ToolNoRecord,
    ToolRateLimited,
    ToolServerError,
    ToolTimeout,
)
from underwriter.workflow.orchestrator import UnderwritingWorkflow


def app(app_id="APP-001"):
    return load_application(DATA_DIR / "applications" / f"{app_id}.json")


class Flaky:
    """Fails with the given errors in order, then returns 'ok'."""

    def __init__(self, *errors: Exception) -> None:
        self.errors, self.calls = list(errors), 0

    def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, s: float) -> None:
        self.delays.append(s)


# -- backoff -------------------------------------------------------------------------------

def test_backoff_ceiling_doubles_then_caps():
    p = RetryPolicy(max_attempts=5, base_s=0.1, cap_s=0.5)
    assert [backoff_ceiling(n, p) for n in (1, 2, 3, 4, 5)] == pytest.approx(
        [0.1, 0.2, 0.4, 0.5, 0.5])
    with pytest.raises(ValueError, match="attempt must be >= 1, got 0"):
        backoff_ceiling(0, p)


def test_backoff_full_jitter_stays_inside_the_ceiling_and_spreads_out():
    p, rng = RetryPolicy(base_s=0.1, cap_s=1.0), random.Random(7)
    draws = [full_jitter(3, p, rng) for _ in range(2000)]
    assert all(0 <= d <= 0.4 for d in draws)
    assert min(draws) < 0.04 and max(draws) > 0.36      # full jitter, not equal jitter
    assert full_jitter(3, p, random.Random(1)) == full_jitter(3, p, random.Random(1))


def test_backoff_retryable_errors_are_the_transient_ones():
    assert set(RETRYABLE) == {ToolTimeout, ToolRateLimited, ToolServerError}
    assert NO_RETRY.max_attempts == 1


def test_backoff_retry_after_is_a_floor():
    p = RetryPolicy(base_s=0.1, cap_s=1.0)
    assert retry_delay(ToolRateLimited("429", retry_after_s=2.0), 1, p, random.Random(0)) == 2.0
    assert retry_delay(ToolTimeout("t"), 1, p, random.Random(0)) <= 0.1


def test_backoff_transient_failures_are_retried_until_success():
    fn, sleep = Flaky(ToolServerError("500"), ToolTimeout("t")), Sleeps()
    value, attempts = call_with_retry(fn, RetryPolicy(max_attempts=3), sleep=sleep,
                                      rng=random.Random(3))
    assert (value, attempts, fn.calls, len(sleep.delays)) == ("ok", 3, 3, 2)
    assert sleep.delays[0] <= 0.1 and sleep.delays[1] <= 0.2


@pytest.mark.parametrize("exc", [ToolNoRecord("none"), ToolMalformed("bad"), KeyError("bug")])
def test_backoff_permanent_failures_are_not_retried(exc):
    fn, sleep = Flaky(exc), Sleeps()
    with pytest.raises(type(exc)):
        call_with_retry(fn, RetryPolicy(max_attempts=5), sleep=sleep)
    assert fn.calls == 1 and sleep.delays == []


def test_backoff_the_last_error_is_raised_when_attempts_run_out():
    fn = Flaky(ToolServerError("a"), ToolServerError("b"), ToolServerError("c"))
    with pytest.raises(ToolServerError, match="c"):
        call_with_retry(fn, RetryPolicy(max_attempts=3), sleep=Sleeps())
    assert fn.calls == 3


def test_backoff_never_sleeps_past_the_deadline():
    fn, sleep = Flaky(ToolRateLimited("429", retry_after_s=5.0)), Sleeps()
    with pytest.raises(ToolRateLimited):
        call_with_retry(fn, RetryPolicy(max_attempts=3), sleep=sleep, clock=lambda: 100.0,
                        deadline=103.0)
    assert sleep.delays == [] and fn.calls == 1


# -- the flaky fault and retries inside a check -----------------------------------------------

def test_backoff_flaky_fault_fails_n_times_then_works():
    plan = FaultPlan.parse("credit_bureau=flaky:2")
    for _ in range(2):
        with pytest.raises(ToolServerError, match="flaky"):
            plan.raise_if_faulted("credit_bureau")
    plan.raise_if_faulted("credit_bureau")
    with pytest.raises(ValueError, match="flaky:<n>"):
        FaultPlan.parse("credit_bureau=wobbly")


def test_backoff_a_check_recovers_with_retries_and_records_attempts():
    spec = next(s for s in CHECKS if s.name == "credit_bureau")
    plan = FaultPlan.parse("credit_bureau=flaky:2")
    r = run_check(spec, app(), plan, retry=RetryPolicy(max_attempts=3), sleep=Sleeps())
    assert r.status == CheckStatus.OK and r.attempts == 3
    no_retry = run_check(spec, app(), FaultPlan.parse("credit_bureau=flaky:1"))
    assert no_retry.status == CheckStatus.UNAVAILABLE and no_retry.attempts == 1


# -- concurrency and the deadline --------------------------------------------------------------

LATENCY = ",".join(f"{s.name}=latency:300" for s in CHECKS)


def test_parallel_checks_run_concurrently():
    a, plan = app(), FaultPlan.parse(LATENCY)
    t0 = time.perf_counter()
    seq = run_checks(a, plan)
    t_seq = time.perf_counter() - t0
    t0 = time.perf_counter()
    con = run_checks_concurrently(a, FaultPlan.parse(LATENCY))
    t_con = time.perf_counter() - t0
    assert [r.status for r in seq] == [r.status for r in con]
    assert t_seq >= 1.2 and t_con < t_seq * 0.6     # about the slowest, not the sum


def test_parallel_results_keep_the_order_of_the_specs():
    plan = FaultPlan.parse("credit_bureau=latency:300,fraud_screen=latency:100")
    results = run_checks_concurrently(app(), plan)
    assert [r.tool for r in results] == [s.name for s in CHECKS]


def test_parallel_a_check_past_the_deadline_is_unavailable_not_waited_for():
    plan = FaultPlan.parse("credit_bureau=latency:3000")
    t0 = time.perf_counter()
    results = run_checks_concurrently(app(), plan, deadline_s=0.5)
    elapsed = time.perf_counter() - t0
    bureau = next(r for r in results if r.tool == "credit_bureau")
    assert elapsed < 2.0
    assert bureau.status == CheckStatus.UNAVAILABLE
    assert bureau.reason == "deadline of 0.5s exceeded" and bureau.latency_ms == 500.0
    assert all(r.status == CheckStatus.OK for r in results if r.tool != "credit_bureau")


def test_parallel_module_constants_are_read_at_call_time(monkeypatch):
    monkeypatch.setattr(parallel, "CHECKS_DEADLINE_S", 0.3)
    results = run_checks_concurrently(app(), FaultPlan.parse("bank_data=latency:2000"))
    assert next(r for r in results if r.tool == "bank_data").reason == "deadline of 0.3s exceeded"


# -- end to end: the decision rules don't change -------------------------------------------------

def test_flaky_bureau_recovers_and_the_decision_stands():
    d = UnderwritingWorkflow(faults=FaultPlan.parse("credit_bureau=flaky:1")).run(app())
    assert d.recommendation == Recommendation.APPROVE
    check = next(e for e in d.audit_trail if e.actor == "tool:credit_bureau")
    assert check.data["attempts"] == 2


def test_slow_required_check_escalates_within_the_deadline(monkeypatch):
    monkeypatch.setattr(parallel, "CHECKS_DEADLINE_S", 0.5)
    t0 = time.perf_counter()
    d = UnderwritingWorkflow(faults=FaultPlan.parse("credit_bureau=latency:3000")).run(app())
    assert time.perf_counter() - t0 < 3.0
    assert d.recommendation == Recommendation.MANUAL_REVIEW
    assert ReasonCode.CREDIT_DATA_UNAVAILABLE in d.reason_codes


def test_slow_optional_check_costs_corroboration_only(monkeypatch):
    monkeypatch.setattr(parallel, "CHECKS_DEADLINE_S", 0.5)
    d = UnderwritingWorkflow(faults=FaultPlan.parse("bank_data=latency:3000")).run(app())
    assert d.recommendation == Recommendation.APPROVE
