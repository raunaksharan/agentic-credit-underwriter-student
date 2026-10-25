"""The underwriting pipeline: the lesson 1 architecture as running code.

    Application -> Income verification -> Credit bureau (tool)
                -> [credit | financial | fraud | policy] analyses
                -> Underwriting agent (proposal) -> Decision engine (decision)
                -> Human review (if escalated) -> Decision + audit trail

Lesson 5 turns this sequence into a LangGraph state machine with checkpoints;
lesson 8 runs the analyses concurrently. The contracts stay the same.
"""

from __future__ import annotations

from underwriter.decision.engine import DecisionEngine
from underwriter.decision.policy import POLICY_VERSION
from underwriter.domain.models import (
    AuditEvent,
    LoanApplication,
    Recommendation,
    UnderwritingCase,
    UnderwritingDecision,
)
from underwriter.pipeline.contracts import Analyzer, IncomeVerifier, ReviewQueue, UnderwritingAgent
from underwriter.pipeline.services import (
    CreditAnalyzer,
    DocumentIncomeVerifier,
    FinancialAnalyzer,
    FraudAnalyzer,
    InMemoryReviewQueue,
    RulesUnderwritingAgent,
    StaticPolicyAnalyzer,
)
from underwriter.tools.bureau import CreditBureau, CreditDataUnavailable, FileCreditBureau


class UnderwritingPipeline:
    def __init__(
        self,
        income_verifier: IncomeVerifier | None = None,
        bureau: CreditBureau | None = None,
        analyzers: list[Analyzer] | None = None,
        agent: UnderwritingAgent | None = None,
        engine: DecisionEngine | None = None,
        review_queue: ReviewQueue | None = None,
    ) -> None:
        self.income_verifier = income_verifier or DocumentIncomeVerifier()
        self.bureau = bureau or FileCreditBureau()
        self.analyzers = analyzers or [CreditAnalyzer(), FinancialAnalyzer(), FraudAnalyzer()]
        self.policy_analyzer = StaticPolicyAnalyzer()
        self.agent = agent or RulesUnderwritingAgent()
        self.engine = engine or DecisionEngine()
        self.review_queue = review_queue or InMemoryReviewQueue()

    def run(self, app: LoanApplication) -> UnderwritingDecision:
        audit: list[AuditEvent] = []

        def log(step: str, actor: str, summary: str, **data) -> None:
            audit.append(AuditEvent(step=step, actor=actor, summary=summary, data=data))

        log("intake", "pipeline", f"Received {app.application_id}",
            documents=[d.doc_type.value for d in app.documents])

        income, income_result = self.income_verifier.verify(app)
        log("income_verification", "income_verification",
            f"Verified monthly income: {income.monthly_gross_income}", method=income.method)

        try:
            credit = self.bureau.get_credit_report(app.applicant.national_id_last4,
                                                   app.applicant.full_name)
            log("credit_bureau", "tool:get_credit_report", f"Score {credit.score}")
        except CreditDataUnavailable as exc:
            credit = None
            log("credit_bureau", "tool:get_credit_report", "Unavailable", error=str(exc))

        case = UnderwritingCase(application=app, verified_income=income,
                                credit_profile=credit, analyses=[income_result])
        for analyzer in self.analyzers:
            result = analyzer.analyze(case)
            case.analyses.append(result)
            log("analysis", analyzer.name, f"{len(result.signals)} signals",
                metrics=result.metrics, signals=[s.code.value for s in result.signals])
        case.analyses.append(self.policy_analyzer.analyze(case))

        proposal = self.agent.recommend(case)
        log("agent", f"agent:{getattr(self.agent, 'model', 'unknown')}",
            f"Proposed {proposal.recommendation.value}: {proposal.rationale}")

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
