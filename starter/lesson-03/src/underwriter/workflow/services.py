"""Lesson 1 implementations of the service contracts.

Everything here is deterministic. Later lessons replace individual services
(policy analyzer -> RAG, agent -> LLM) without touching the others.
"""

from __future__ import annotations

from datetime import date

from underwriter.domain.models import (
    AgentRecommendation,
    AnalysisResult,
    DocumentType,
    Evidence,
    LoanApplication,
    ReasonCode,
    Recommendation,
    RiskSignal,
    UnderwritingCase,
    UnderwritingDecision,
    VerifiedIncome,
)
from underwriter.ingestion.documents import (
    DocumentStore,
    extract_bank_statement,
    extract_payslip,
)
from underwriter.risk.calculations import (
    income_discrepancy,
    monthly_payment,
    post_loan_dti,
)

AS_OF = date(2026, 10, 5)  # fixed "today" so sample runs are reproducible


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())


# ---------------------------------------------------------------------------
# Income verification (policy section 5)
# ---------------------------------------------------------------------------


class DocumentIncomeVerifier:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or DocumentStore()

    def verify(self, app: LoanApplication) -> tuple[VerifiedIncome, AnalysisResult]:
        result = AnalysisResult(service="income_verification")
        self_employed = app.employment.employment_type == "self_employed"
        required = DocumentType.TAX_RETURN if self_employed else DocumentType.PAYSLIP
        path = self.store.find(app, required)

        if path is None:
            result.signals += [
                RiskSignal(code=ReasonCode.MISSING_DOCUMENT, severity="review",
                           message=f"Required {required.value} was not submitted.",
                           evidence=[Evidence(source="policy:5.3" if self_employed
                                              else "policy:5.2",
                                              detail=f"{required.value} required")]),
                RiskSignal(code=ReasonCode.INCOME_UNVERIFIED, severity="review",
                           message="Income cannot be verified; DTI cannot be computed."),
            ]
            return VerifiedIncome(monthly_gross_income=None, method="unverified"), result

        if self_employed:  # tax-return extraction arrives with LLM extraction in lesson 3
            raise NotImplementedError("tax return extraction is built in lesson 3")

        slip = extract_payslip(self.store.read(path), source=path)
        evidence = [Evidence(source=path,
                             detail=f"Gross pay this period {slip.monthly_gross:,.2f}")]

        bank_path = self.store.find(app, DocumentType.BANK_STATEMENT)
        if bank_path:
            stmt = extract_bank_statement(self.store.read(bank_path), source=bank_path)
            payroll = stmt.deposits_matching("payroll")
            if payroll:
                evidence.append(Evidence(source=bank_path,
                                         detail=f"{len(payroll)} payroll deposits found"))
            else:
                result.signals.append(RiskSignal(
                    code=ReasonCode.INCOME_UNVERIFIED, severity="info",
                    message="No payroll deposits found to corroborate the payslip.",
                    evidence=[Evidence(source=bank_path, detail="no PAYROLL credits")]))

        gap = income_discrepancy(app.employment.stated_annual_income, slip.monthly_gross)
        result.metrics.update(verified_monthly_income=slip.monthly_gross,
                              income_discrepancy=round(gap, 4))
        result.evidence = evidence
        return VerifiedIncome(monthly_gross_income=slip.monthly_gross, method="payslip",
                              evidence=evidence), result


# ---------------------------------------------------------------------------
# Parallel analyzers
# ---------------------------------------------------------------------------


class CreditAnalyzer:
    name = "credit_analysis"

    def analyze(self, case: UnderwritingCase) -> AnalysisResult:
        r = AnalysisResult(service=self.name)
        cp = case.credit_profile
        if cp is None:
            r.signals.append(RiskSignal(
                code=ReasonCode.CREDIT_DATA_UNAVAILABLE, severity="review",
                message="No credit report available. Score must not be estimated.",
                evidence=[Evidence(source="policy:3.4", detail="route to manual review")]))
            return r
        r.metrics.update(credit_score=cp.score,
                         delinquencies_last_24m=cp.delinquencies_last_24m,
                         credit_history_months=cp.credit_history_months)
        r.evidence.append(Evidence(source="bureau:credit_report",
                                   detail=f"score {cp.score}, {cp.delinquencies_last_24m} "
                                          f"delinquencies/24m"))
        return r


class FinancialAnalyzer:
    name = "financial_analysis"

    def analyze(self, case: UnderwritingCase) -> AnalysisResult:
        r = AnalysisResult(service=self.name)
        app = case.application
        payment = monthly_payment(app.loan.amount, app.loan.annual_interest_rate,
                                  app.loan.term_months)
        r.metrics["new_monthly_payment"] = round(payment, 2)
        r.metrics["employment_tenure_months"] = _months_between(app.employment.start_date, AS_OF)

        income = case.verified_income.monthly_gross_income
        if income is None:
            return r  # already flagged by income verification; never guess

        reported = case.credit_profile.reported_monthly_debt if case.credit_profile else 0.0
        existing = max(app.existing_monthly_debt_payments, reported)  # policy 4.4
        dti = post_loan_dti(existing, payment, income)
        r.metrics.update(post_loan_dti=round(dti, 4),
                         loan_to_annual_income=round(app.loan.amount / (income * 12), 4))
        r.evidence.append(Evidence(
            source="calc:post_loan_dti",
            detail=f"({existing:,.2f} + {payment:,.2f}) / {income:,.2f} = {dti:.1%}"))
        return r


class FraudAnalyzer:
    name = "fraud_checks"

    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or DocumentStore()

    def analyze(self, case: UnderwritingCase) -> AnalysisResult:
        r = AnalysisResult(service=self.name)
        app = case.application
        path = self.store.find(app, DocumentType.PAYSLIP)
        if path is None:
            return r
        slip = extract_payslip(self.store.read(path), source=path)
        if _normalize_name(slip.employee_name) != _normalize_name(app.applicant.full_name):
            r.signals.append(RiskSignal(
                code=ReasonCode.IDENTITY_MISMATCH, severity="review",
                message=f"Payslip names '{slip.employee_name}', application names "
                        f"'{app.applicant.full_name}'.",
                evidence=[Evidence(source=path, detail="Employee field"),
                          Evidence(source="policy:8.1", detail="names must match")]))
        if _normalize_name(slip.employer) != _normalize_name(app.employment.employer_name):
            r.signals.append(RiskSignal(
                code=ReasonCode.FRAUD_SIGNAL, severity="review",
                message="Employer on payslip differs from the application.",
                evidence=[Evidence(source=path, detail="Employer field")]))
        return r


class StaticPolicyAnalyzer:
    """Lesson 1 placeholder, kept as the "before" for lesson 2.

    Replaced in the workflow by rag.analyzer.RetrievalPolicyAnalyzer.

    Returns the policy sections that apply to this case so every decision can cite
    policy. In lesson 2 this becomes hybrid retrieval over the policy corpus, and
    students measure whether retrieval finds the same sections.
    """

    name = "policy_analysis"

    SECTIONS = {
        "credit_score": "3", "post_loan_dti": "4", "income_discrepancy": "5",
        "delinquencies_last_24m": "6", "loan_to_annual_income": "7",
    }

    def analyze(self, case: UnderwritingCase) -> AnalysisResult:
        r = AnalysisResult(service=self.name)
        for metric, section in self.SECTIONS.items():
            if metric in case.metrics:
                r.evidence.append(Evidence(source=f"policy:{section}",
                                           detail=f"governs {metric}"))
        return r


# ---------------------------------------------------------------------------
# Underwriting agent (stub) and review queue
# ---------------------------------------------------------------------------


class RulesUnderwritingAgent:
    """Stand-in for the LLM underwriting agent (lesson 3+).

    Its heuristics are deliberately simpler and looser than policy (e.g. a 45% DTI
    cut-off instead of 43%), so you can watch the decision engine override it. An
    LLM will also be "approximately right"; the architecture must not depend on it
    being exactly right.
    """

    model = "rules-stub-v1"

    def recommend(self, case: UnderwritingCase) -> AgentRecommendation:
        m = case.metrics
        risk_factors = [s.message for s in case.all_signals if s.severity != "info"]
        missing = [s.message for s in case.all_signals
                   if s.code in (ReasonCode.MISSING_DOCUMENT, ReasonCode.CREDIT_DATA_UNAVAILABLE)]

        if risk_factors:
            rec, why = Recommendation.MANUAL_REVIEW, "Open risk or data-quality signals."
        elif m.get("credit_score", 999) < 600:
            rec, why = Recommendation.DECLINE, "Credit score is weak."
        elif m.get("post_loan_dti", 0) > 0.45:
            rec, why = Recommendation.MANUAL_REVIEW, "Debt burden is high after this loan."
        else:
            rec, why = Recommendation.APPROVE, "Income, credit and affordability look sound."

        evidence = [e for a in case.analyses for e in a.evidence]
        return AgentRecommendation(recommendation=rec, rationale=why, risk_factors=risk_factors,
                                   missing_information=missing, evidence=evidence)


class InMemoryReviewQueue:
    def __init__(self) -> None:
        self.cases: dict[str, UnderwritingDecision] = {}

    def submit(self, decision: UnderwritingDecision) -> str:
        case_id = f"REV-{decision.application_id}"
        self.cases[case_id] = decision
        return case_id
