"""Domain contracts for the underwriting platform.

Lesson 1 principle: every service boundary in the architecture is a typed
contract. LLM-backed components added in later lessons must produce these
same types, which is what lets us test, swap and audit them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Recommendation(StrEnum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class DocumentType(StrEnum):
    PAYSLIP = "payslip"
    BANK_STATEMENT = "bank_statement"
    TAX_RETURN = "tax_return"
    EMPLOYMENT_LETTER = "employment_letter"
    ID_PROOF = "id_proof"


class ReasonCode(StrEnum):
    """Machine-readable reasons. Every escalation or decline must cite at least one."""

    # Data availability: the system must never invent these values.
    CREDIT_DATA_UNAVAILABLE = "CREDIT_DATA_UNAVAILABLE"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    INCOME_UNVERIFIED = "INCOME_UNVERIFIED"
    # Consistency
    INCOME_MISMATCH = "INCOME_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    # Policy
    DTI_ABOVE_REVIEW_THRESHOLD = "DTI_ABOVE_REVIEW_THRESHOLD"
    DTI_ABOVE_MAX = "DTI_ABOVE_MAX"
    CREDIT_SCORE_BELOW_MIN = "CREDIT_SCORE_BELOW_MIN"
    CREDIT_SCORE_REVIEW_BAND = "CREDIT_SCORE_REVIEW_BAND"
    RECENT_DELINQUENCY = "RECENT_DELINQUENCY"
    LOAN_AMOUNT_ABOVE_LIMIT = "LOAN_AMOUNT_ABOVE_LIMIT"
    EMPLOYMENT_TENURE_SHORT = "EMPLOYMENT_TENURE_SHORT"
    # Fraud
    FRAUD_SIGNAL = "FRAUD_SIGNAL"
    # AI components (lesson 3 onward): the model failed, so a human decides
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    # Positive
    MEETS_ALL_CRITERIA = "MEETS_ALL_CRITERIA"


# ---------------------------------------------------------------------------
# Input: what arrives from the loan origination system
# ---------------------------------------------------------------------------


class Address(BaseModel):
    line1: str
    city: str
    state: str
    postal_code: str


class Applicant(BaseModel):
    full_name: str
    date_of_birth: date
    national_id_last4: str = Field(min_length=4, max_length=4)
    email: str
    address: Address


class Employment(BaseModel):
    employer_name: str
    job_title: str
    employment_type: str = Field(description="full_time | part_time | self_employed | contract")
    start_date: date
    stated_annual_income: float = Field(gt=0)


class LoanRequest(BaseModel):
    amount: float = Field(gt=0)
    term_months: int = Field(gt=0, le=120)
    purpose: str
    annual_interest_rate: float = Field(gt=0, lt=1, description="e.g. 0.129 for 12.9% APR")


class DocumentRef(BaseModel):
    doc_type: DocumentType
    path: str = Field(description="Path relative to the data/ directory")


class LoanApplication(BaseModel):
    application_id: str
    submitted_at: datetime
    applicant: Applicant
    employment: Employment
    loan: LoanRequest
    existing_monthly_debt_payments: float = Field(ge=0)
    documents: list[DocumentRef]


# ---------------------------------------------------------------------------
# Intermediate: normalized facts produced by ingestion and analysis services
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """A pointer to where a fact came from. Every claim in a decision needs one."""

    source: str = Field(description="document path, API name, or policy section id")
    detail: str


class VerifiedIncome(BaseModel):
    monthly_gross_income: float | None
    method: str = Field(description="How it was derived, e.g. 'payslip_ytd' or 'bank_deposits'")
    evidence: list[Evidence] = []


class CreditProfile(BaseModel):
    score: int = Field(ge=300, le=900)
    open_accounts: int
    delinquencies_last_24m: int
    credit_history_months: int
    reported_monthly_debt: float


class RiskSignal(BaseModel):
    code: ReasonCode
    severity: str = Field(description="info | review | decline")
    message: str
    evidence: list[Evidence] = []


class AnalysisResult(BaseModel):
    """Output of one analysis service in the parallel fan-out."""

    service: str
    signals: list[RiskSignal] = []
    metrics: dict[str, float] = {}
    evidence: list[Evidence] = []


class UnderwritingCase(BaseModel):
    """Everything the decision step needs, assembled by the orchestrator."""

    application: LoanApplication
    verified_income: VerifiedIncome
    credit_profile: CreditProfile | None
    analyses: list[AnalysisResult] = []

    @property
    def all_signals(self) -> list[RiskSignal]:
        return [s for a in self.analyses for s in a.signals]

    @property
    def metrics(self) -> dict[str, float]:
        merged: dict[str, float] = {}
        for a in self.analyses:
            merged.update(a.metrics)
        return merged


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class AgentRecommendation(BaseModel):
    """What the underwriting agent proposes. In lesson 1 a rules stub produces it;
    from lesson 3 an LLM does. Either way it is a *proposal*, not the decision."""

    recommendation: Recommendation
    rationale: str
    risk_factors: list[str] = []
    missing_information: list[str] = []
    evidence: list[Evidence] = []
    # provenance (lesson 3): which model and prompt produced this, and did it validate?
    model: str = "rules-stub-v1"
    prompt_version: str | None = None
    attempts: int = 1
    valid: bool = True
    failure: ReasonCode | None = Field(
        default=None, description="INVALID_MODEL_OUTPUT or MODEL_UNAVAILABLE when not valid")
    validation_errors: list[str] = []
    input_tokens: int = 0
    output_tokens: int = 0


class AuditEvent(BaseModel):
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    step: str
    actor: str = Field(description="service name, 'llm:<model>', or 'human:<id>'")
    summary: str
    data: dict = {}


class UnderwritingDecision(BaseModel):
    application_id: str
    recommendation: Recommendation
    reason_codes: list[ReasonCode]
    agent_recommendation: AgentRecommendation
    overridden_by_policy: bool = Field(
        description="True when the deterministic decision engine changed the agent's proposal"
    )
    requires_human_review: bool
    metrics: dict[str, float]
    audit_trail: list[AuditEvent]
