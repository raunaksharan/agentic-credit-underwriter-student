"""Context engineering: decide exactly what the model sees.

Three rules:

1. **Minimise.** The model never sees the applicant's name, date of birth, ID
   digits, email or address. It doesn't need them to judge affordability, and what it
   never sees it can never leak or be biased by.
2. **Give everything an id.** Every fact, signal, document and policy excerpt carries
   an id the model must cite. That makes citations checkable (validators.py).
3. **Prioritise within a budget.** Signals first, then metrics, then policy excerpts,
   then the application summary. Policy excerpts are trimmed and, if needed, dropped,
   lowest priority first, so the prompt stays under MAX_CONTEXT_CHARS.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from underwriter.domain.models import UnderwritingCase

MAX_CONTEXT_CHARS = 6000
EXCERPT_CHARS = 360
RATIO_METRICS = {"post_loan_dti", "income_discrepancy", "loan_to_annual_income"}


class CaseContext(BaseModel):
    payload: dict
    allowed_ids: dict[str, str]  # id -> human-readable description, for evidence
    dropped_policy: int = 0

    @property
    def as_json(self) -> str:
        return json.dumps(self.payload, indent=1, ensure_ascii=False)


def build_context(case: UnderwritingCase, max_chars: int = MAX_CONTEXT_CHARS) -> CaseContext:
    app = case.application
    allowed: dict[str, str] = {}

    signals = []
    for s in case.all_signals:
        sid = f"signal:{s.code.value}"
        allowed[sid] = s.message
        signals.append({"id": sid, "code": s.code.value, "severity": s.severity,
                        "message": s.message})

    metrics = {}
    for name, value in sorted(case.metrics.items()):
        mid = f"metric:{name}"
        allowed[mid] = f"{name} = {value}"
        metrics[name] = {"id": mid, "value": value,
                         "unit": "fraction" if name in RATIO_METRICS else None}

    documents = []
    for d in app.documents:
        did = f"doc:{d.path}"
        allowed[did] = d.doc_type.value
        documents.append({"id": did, "type": d.doc_type.value})

    policy = []
    for a in case.analyses:
        if a.service != "policy_analysis":
            continue
        for e in a.evidence:
            citation, _, text = e.detail.partition(": ")
            policy.append({"id": e.source, "citation": citation,
                           "excerpt": text[:EXCERPT_CHARS]})
            allowed[e.source] = citation

    payload = {
        "application": {
            "application_id": app.application_id,
            "loan": app.loan.model_dump(),
            "employment_type": app.employment.employment_type,
            "stated_annual_income": app.employment.stated_annual_income,
            "existing_monthly_debt_payments": app.existing_monthly_debt_payments,
        },
        "signals": signals,
        "metrics": metrics,
        "policy": policy,
        "documents": documents,
    }
    dropped = 0
    while len(json.dumps(payload, indent=1, ensure_ascii=False)) > max_chars and payload["policy"]:
        gone = payload["policy"].pop()  # lowest priority last
        allowed.pop(gone["id"], None)
        dropped += 1
    return CaseContext(payload=payload, allowed_ids=allowed, dropped_policy=dropped)
