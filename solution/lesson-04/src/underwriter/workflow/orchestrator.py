"""The underwriting workflow: the lesson 1 architecture as running code.

    Application -> Income verification -> External checks (credit, fraud, bank, employment)
                -> [credit | financial | fraud | policy] analyses
                -> Underwriting agent (proposal) -> Decision engine (decision)
                -> Human review (if escalated) -> Decision + audit trail

Lesson 5 turns this sequence into a LangGraph state machine with checkpoints;
lesson 8 runs the analyses concurrently. The contracts stay the same.
"""

from __future__ import annotations

from underwriter.agents.factory import get_agent
from underwriter.decision.engine import DecisionEngine
from underwriter.decision.policy import POLICY_VERSION
from underwriter.domain.models import (
    AuditEvent,
    CheckStatus,
    CreditProfile,
    LoanApplication,
    Recommendation,
    UnderwritingCase,
    UnderwritingDecision,
)
from underwriter.rag.analyzer import RetrievalPolicyAnalyzer
from underwriter.tools.checks import CHECKS, CheckSpec, run_checks
from underwriter.tools.faults import FaultPlan
from underwriter.workflow.contracts import Analyzer, IncomeVerifier, ReviewQueue, UnderwritingAgent
from underwriter.workflow.services import (
    ChecksAnalyzer,
    CreditAnalyzer,
    DocumentIncomeVerifier,
    FinancialAnalyzer,
    FraudAnalyzer,
    InMemoryReviewQueue,
)


class UnderwritingWorkflow:
    def __init__(
        self,
        income_verifier: IncomeVerifier | None = None,
        checks: list[CheckSpec] | None = None,
        faults: FaultPlan | None = None,
        analyzers: list[Analyzer] | None = None,
        agent: UnderwritingAgent | None = None,
        engine: DecisionEngine | None = None,
        review_queue: ReviewQueue | None = None,
        policy_analyzer: Analyzer | None = None,
    ) -> None:
        self.income_verifier = income_verifier or DocumentIncomeVerifier()
        self.checks = checks or CHECKS  # lesson 4: external checks as typed tools
        self.faults = faults if faults is not None else FaultPlan.from_env()
        self.analyzers = analyzers or [CreditAnalyzer(), FinancialAnalyzer(), FraudAnalyzer(),
                                       ChecksAnalyzer()]
        self.policy_analyzer = policy_analyzer or RetrievalPolicyAnalyzer()  # lesson 2
        self.agent = agent or get_agent()  # lesson 3: LLM; lesson 4: tool-calling
        self.engine = engine or DecisionEngine()
        self.review_queue = review_queue or InMemoryReviewQueue()

    def run(self, app: LoanApplication) -> UnderwritingDecision:
        case, audit = self.assemble_case(app)
        return self.decide(case, audit)

    def assemble_case(self, app: LoanApplication) -> tuple[UnderwritingCase, list[AuditEvent]]:
        """Everything before the agent: verified facts, analyses and policy citations."""
        audit: list[AuditEvent] = []

        def log(step: str, actor: str, summary: str, **data) -> None:
            audit.append(AuditEvent(step=step, actor=actor, summary=summary, data=data))

        log("intake", "workflow", f"Received {app.application_id}",
            documents=[d.doc_type.value for d in app.documents])

        income, income_result = self.income_verifier.verify(app)
        log("income_verification", "income_verification",
            f"Verified monthly income: {income.monthly_gross_income}", method=income.method)

        checks = run_checks(app, self.faults, self.checks)
        for c in checks:
            summary = c.status.value + (f": {c.reason}" if c.reason else "")
            log("check", f"tool:{c.tool}", summary, required=c.required,
                latency_ms=c.latency_ms, attempts=c.attempts)
        credit_check = next((c for c in checks if c.tool == "credit_bureau"), None)
        credit = (CreditProfile.model_validate(credit_check.data)
                  if credit_check and credit_check.status == CheckStatus.OK else None)

        case = UnderwritingCase(application=app, verified_income=income,
                                credit_profile=credit, analyses=[income_result], checks=checks)
        for analyzer in self.analyzers:
            result = analyzer.analyze(case)
            case.analyses.append(result)
            log("analysis", analyzer.name, f"{len(result.signals)} signals",
                metrics=result.metrics, signals=[s.code.value for s in result.signals])
        policy = self.policy_analyzer.analyze(case)
        case.analyses.append(policy)
        log("policy_retrieval", self.policy_analyzer.name,
            f"{len(policy.evidence)} citations", citations=[e.source for e in policy.evidence])
        return case, audit

    def decide(self, case: UnderwritingCase, audit: list[AuditEvent]) -> UnderwritingDecision:
        """The agent proposes, the engine decides, a human reviews if escalated."""
        app = case.application

        def log(step: str, actor: str, summary: str, **data) -> None:
            audit.append(AuditEvent(step=step, actor=actor, summary=summary, data=data))

        proposal = self.agent.recommend(case)
        log("agent", f"agent:{proposal.model}",
            f"Proposed {proposal.recommendation.value}: {proposal.rationale}",
            prompt_version=proposal.prompt_version, attempts=proposal.attempts,
            valid=proposal.valid, validation_errors=proposal.validation_errors,
            input_tokens=proposal.input_tokens, output_tokens=proposal.output_tokens)

        result = self.engine.decide(case, proposal)
        log("decision_engine", f"engine:{POLICY_VERSION}",
            f"Decided {result.recommendation.value}"
            + (" (overrode agent)" if result.overridden_by_policy else ""),
            findings=[f.model_dump(mode="json") for f in result.findings])

        decision = UnderwritingDecision(
            application_id=app.application_id,
            recommendation=result.recommendation,
            reason_codes=result.reason_codes,
            agent_recommendation=proposal,
            overridden_by_policy=result.overridden_by_policy,
            requires_human_review=result.recommendation == Recommendation.MANUAL_REVIEW,
            metrics=case.metrics,
            audit_trail=audit,
        )
        if decision.requires_human_review:
            case_id = self.review_queue.submit(decision)
            decision.audit_trail.append(AuditEvent(step="human_review", actor="review_queue",
                                                   summary=f"Escalated as {case_id}"))
        return decision
