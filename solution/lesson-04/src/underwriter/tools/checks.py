"""External checks: fake tools behind one wrapper that never returns None.

    run_check(spec, app, faults) -> CheckResult(OK | UNAVAILABLE | INVALID, reason)

Each fake reads the synthetic data in data/ the way a real integration would read
an API. Lesson 8 runs these concurrently under a deadline and adds retries; the
contract (a typed result per check) stays the same.
"""

from __future__ import annotations

import csv
import io
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
        raise ToolNoRecord(str(exc)) from exc
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


def run_check(spec: CheckSpec, app: LoanApplication, faults: FaultPlan | None = None
              ) -> CheckResult:
    """Call one tool. Every exception becomes a typed status, never a missing value."""
    faults = faults or FaultPlan()
    start = time.perf_counter()

    def result(status: CheckStatus, data: dict | None = None, reason: str = "") -> CheckResult:
        return CheckResult(tool=spec.name, required=spec.required, status=status,
                           data=data or {}, reason=reason,
                           latency_ms=round((time.perf_counter() - start) * 1000, 2))

    try:
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
        return result(CheckStatus.OK, data)
    except ToolMalformed as exc:
        return result(CheckStatus.INVALID, reason=str(exc))
    except ToolRateLimited as exc:
        return result(CheckStatus.UNAVAILABLE, reason=f"{exc} (retry after {exc.retry_after_s}s)")
    except ToolError as exc:
        return result(CheckStatus.UNAVAILABLE, reason=str(exc))


def run_checks(app: LoanApplication, faults: FaultPlan | None = None,
               specs: list[CheckSpec] | None = None) -> list[CheckResult]:
    """All checks, one after another. Lesson 8 makes this concurrent."""
    return [run_check(spec, app, faults) for spec in (specs or CHECKS)]
