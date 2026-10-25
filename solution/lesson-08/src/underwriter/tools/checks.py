"""External checks: fake tools behind one wrapper that never returns None.

    run_check(spec, app, faults) -> CheckResult(OK | UNAVAILABLE | INVALID, reason)

Each fake reads the synthetic data in data/ the way a real integration would read
an API. Lesson 8 adds retries (`retry=`, with full jitter, inside a deadline) and runs
the checks concurrently (reliability/parallel.py); the contract (a typed result per
check) stays the same. `attempts` on the result says how many calls it took.
"""

from __future__ import annotations

import csv
import io
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import ValidationError

from underwriter.domain.models import (
    CheckResult,
    CheckStatus,
    CreditProfile,
    DocumentType,
    LoanApplication,
)
from underwriter.ingestion.documents import DocumentStore
from underwriter.reliability.backoff import NO_RETRY, RetryPolicy, call_with_retry
from underwriter.tools.bureau import CreditDataUnavailable, FileCreditBureau
from underwriter.tools.faults import (
    FaultPlan,
    ToolError,
    ToolMalformed,
    ToolNoRecord,
    ToolRateLimited,
)


@dataclass(frozen=True)
class CheckSpec:
    name: str
    required: bool
    description: str
    fn: Callable[[LoanApplication], dict]


# -- the fake tools -------------------------------------------------------------

_bureau = FileCreditBureau()
_store = DocumentStore()


def credit_bureau(app: LoanApplication) -> dict:
    try:
        report = _bureau.get_credit_report(app.applicant.national_id_last4,
                                           app.applicant.full_name)
    except CreditDataUnavailable as exc:
        # The bureau's own message names the applicant's id digits. Our message must not:
        # it flows into signals, the LLM context and traces (found in lesson 7).
        raise ToolNoRecord("credit bureau has no record for this applicant") from exc
    return report.model_dump()


def bank_data(app: LoanApplication) -> dict:
    path = _store.find(app, DocumentType.BANK_STATEMENT)
    if path is None:
        raise ToolNoRecord("no bank statement on file")
    rows = list(csv.DictReader(io.StringIO(_store.read(path))))
    payroll = [float(r["amount"]) for r in rows if "PAYROLL" in r["description"]]
    months = len({r["date"][:7] for r in rows})
    return {
        "months": months,
        "avg_monthly_payroll_deposits": round(sum(payroll) / months, 2) if months else 0.0,
        "lowest_balance": min(float(r["balance"]) for r in rows),
        "overdrafts": sum(float(r["balance"]) < 0 for r in rows),
    }


def employment_verification(app: LoanApplication) -> dict:
    path = _store.find(app, DocumentType.EMPLOYMENT_LETTER)
    if path is None:
        return {"verified": False, "source": "none",
                "employer": app.employment.employer_name}
    letter = _store.read(path)
    return {"verified": app.employment.employer_name in letter, "source": "employment_letter",
            "employer": app.employment.employer_name}


def fraud_screen(app: LoanApplication) -> dict:
    # A real vendor scores device, email and address risk; ours is deterministic.
    email_ok = app.applicant.email.endswith(("@example.com", "@example.org"))
    return {"identity_risk": "low" if email_ok else "medium",
            "watchlist_hit": False, "vendor": "fake-fraud-v1"}


CHECKS: list[CheckSpec] = [
    CheckSpec("credit_bureau", True, "Bureau credit report (score, delinquencies, debt)",
              credit_bureau),
    CheckSpec("fraud_screen", True, "Identity and watchlist screening", fraud_screen),
    CheckSpec("bank_data", False, "Bank statement summary to corroborate income", bank_data),
    CheckSpec("employment_verification", False, "Employer confirmation",
              employment_verification),
]

_VALIDATORS: dict[str, Callable[[dict], None]] = {
    "credit_bureau": lambda d: CreditProfile.model_validate(d) and None,
}


# -- the wrapper ------------------------------------------------------------------


def run_check(spec: CheckSpec, app: LoanApplication, faults: FaultPlan | None = None, *,
              retry: RetryPolicy = NO_RETRY, deadline: float | None = None,
              sleep: Callable[[float], None] = time.sleep, rng: random.Random | None = None,
              clock: Callable[[], float] = time.monotonic) -> CheckResult:
    """Call one tool, retrying transient failures. Every exception becomes a typed
    status, never a missing value."""
    from underwriter.observability.tracing import mark_error, redact, set_attrs, span
    with span(f"check {spec.name}", check__tool=spec.name, check__required=spec.required,
              check__fault=(faults or FaultPlan()).for_tool(spec.name)) as s:
        result = _run_check(spec, app, faults, retry=retry, deadline=deadline, sleep=sleep,
                            rng=rng, clock=clock)
        set_attrs(s, check__status=result.status.value, check__latency_ms=result.latency_ms,
                  check__attempts=result.attempts, check__reason=redact(result.reason) or None)
        if result.status != CheckStatus.OK:
            mark_error(s, f"{result.status.value}: {result.reason}")
        return result


def _call_tool(spec: CheckSpec, app: LoanApplication, faults: FaultPlan) -> dict:
    """One attempt: the injected latency and fault, the tool, then validation."""
    delay = faults.latency_ms(spec.name)
    if delay:
        time.sleep(delay / 1000)
    faults.raise_if_faulted(spec.name)
    data = spec.fn(app)
    if faults.for_tool(spec.name) == "malformed":
        data = {"unexpected": "payload", "score": "seven hundred"}
    try:
        _VALIDATORS.get(spec.name, lambda d: None)(data)
    except ValidationError as exc:
        raise ToolMalformed(f"{spec.name}: response failed validation "
                            f"({exc.error_count()} errors)") from exc
    return data


def _run_check(spec: CheckSpec, app: LoanApplication, faults: FaultPlan | None = None, *,
               retry: RetryPolicy = NO_RETRY, deadline: float | None = None,
               sleep: Callable[[float], None] = time.sleep, rng: random.Random | None = None,
               clock: Callable[[], float] = time.monotonic) -> CheckResult:
    faults = faults or FaultPlan()
    start = time.perf_counter()
    attempts = [0]

    def attempt() -> dict:
        attempts[0] += 1
        return _call_tool(spec, app, faults)

    def result(status: CheckStatus, data: dict | None = None, reason: str = "") -> CheckResult:
        return CheckResult(tool=spec.name, required=spec.required, status=status,
                           data=data or {}, reason=reason, attempts=max(1, attempts[0]),
                           latency_ms=round((time.perf_counter() - start) * 1000, 2))

    try:
        data, _ = call_with_retry(attempt, retry, sleep=sleep, rng=rng, clock=clock,
                                  deadline=deadline)
        return result(CheckStatus.OK, data)
    except ToolMalformed as exc:
        return result(CheckStatus.INVALID, reason=str(exc))
    except ToolRateLimited as exc:
        return result(CheckStatus.UNAVAILABLE, reason=f"{exc} (retry after {exc.retry_after_s}s)")
    except ToolError as exc:
        return result(CheckStatus.UNAVAILABLE, reason=str(exc))


def run_checks(app: LoanApplication, faults: FaultPlan | None = None,
               specs: list[CheckSpec] | None = None) -> list[CheckResult]:
    """All checks, one after another, no retries: the baseline that lesson 8's
    reliability/parallel.py is measured against (`underwriter bench`)."""
    return [run_check(spec, app, faults) for spec in (specs or CHECKS)]
