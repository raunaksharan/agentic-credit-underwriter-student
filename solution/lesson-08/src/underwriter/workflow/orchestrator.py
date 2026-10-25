"""The underwriting workflow: the lesson 1 architecture as running code.

    Application -> Income verification -> External checks (credit, fraud, bank, employment)
                -> [credit | financial | fraud | policy] analyses
                -> Underwriting agent (proposal) -> Decision engine (decision)
                -> Human review (if escalated) -> Decision + audit trail

This class owns the components (the lesson 1 contracts). Since lesson 5 the control
flow lives in workflow/graph.py: a LangGraph graph with typed state, per-node
timeouts and retries, and a human-review edge that can pause for a reviewer.
Lesson 8 runs the checks concurrently. The contracts stay the same.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from underwriter.agents.factory import get_agent
from underwriter.decision.engine import DecisionEngine
from underwriter.domain.models import (
    AnalysisResult,
    AuditEvent,
    CheckResult,
    CheckStatus,
    CreditProfile,
    HumanReview,
    LoanApplication,
    UnderwritingCase,
    UnderwritingDecision,
)
from underwriter.observability.metering import Usage, metering
from underwriter.observability.tracing import set_attrs, span
from underwriter.rag.analyzer import RetrievalPolicyAnalyzer
from underwriter.reliability.parallel import run_checks_concurrently
from underwriter.tools.checks import CHECKS, CheckSpec
from underwriter.tools.faults import FaultPlan
from underwriter.workflow.contracts import Analyzer, IncomeVerifier, ReviewQueue, UnderwritingAgent
from underwriter.workflow.resilience import NodeFaults, NodePolicy
from underwriter.workflow.services import (
    ChecksAnalyzer,
    CreditAnalyzer,
    DocumentIncomeVerifier,
    FinancialAnalyzer,
    FraudAnalyzer,
    InMemoryReviewQueue,
)


@dataclass
class PendingReview:
    """An interactive run paused at the human-review edge."""

    thread_id: str
    request: dict
    usage: Usage | None = None


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
        node_faults: NodeFaults | None = None,
        node_policies: dict[str, NodePolicy] | None = None,
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
        self.node_faults = node_faults if node_faults is not None else NodeFaults.from_env()
        self.node_policies = node_policies
        self._graph = None
        self._pending_usage: dict[str, Usage] = {}

    # -- the steps the graph's nodes call --------------------------------------------

    def run_checks(self, app: LoanApplication) -> list[CheckResult]:
        """Lesson 8: concurrently, with retries, under one deadline."""
        return run_checks_concurrently(app, self.faults, self.checks)

    def build_case(self, app: LoanApplication, income, income_result: AnalysisResult,
                   checks: list[CheckResult]) -> UnderwritingCase:
        credit_check = next((c for c in checks if c.tool == "credit_bureau"), None)
        credit = (CreditProfile.model_validate(credit_check.data)
                  if credit_check and credit_check.status == CheckStatus.OK else None)
        return UnderwritingCase(application=app, verified_income=income, credit_profile=credit,
                                analyses=[income_result], checks=checks)

    def run_analyzers(self, case: UnderwritingCase) -> list[AnalysisResult]:
        results = []
        for analyzer in self.analyzers:
            result = analyzer.analyze(case)
            case.analyses.append(result)  # later analyzers may read earlier ones
            results.append(result)
        return results

    # -- running the graph -------------------------------------------------------------

    @property
    def graph(self):
        if self._graph is None:
            from underwriter.workflow.graph import build_graph
            self._graph = build_graph(self, self.node_faults, self.node_policies)
        return self._graph

    def _config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def _invoke(self, app: LoanApplication, interactive: bool):
        """One root span and one usage meter per run (lesson 7)."""
        thread = f"{app.application_id}-{uuid.uuid4().hex[:8]}"
        start = time.perf_counter()
        with metering() as meter, span(f"underwrite {app.application_id}",
                                       application__id=app.application_id,
                                       loan__amount=app.loan.amount,
                                       workflow__interactive=interactive,
                                       workflow__thread=thread) as s:
            state = self.graph.invoke({"application": app, "interactive": interactive,
                                       "audit": []}, self._config(thread))
            meter.usage.total_ms = round((time.perf_counter() - start) * 1000, 1)
            usage = meter.usage.model_copy(deep=True)
            decision = state.get("decision")
            if "__interrupt__" in state:
                set_attrs(s, workflow__paused_for_review=True)
            elif decision is not None:
                set_attrs(s, decision__recommendation=decision.recommendation.value,
                          decision__reason_codes=[r.value for r in decision.reason_codes],
                          llm__input_tokens=usage.input_tokens,
                          llm__output_tokens=usage.output_tokens,
                          llm__cost_usd=usage.cost_usd)
        return thread, state, usage

    def run(self, app: LoanApplication) -> UnderwritingDecision:
        """Non-interactive: escalated cases are queued and the run ends."""
        _, state, usage = self._invoke(app, interactive=False)
        decision = state["decision"]
        decision.usage = usage
        return decision

    def start(self, app: LoanApplication) -> UnderwritingDecision | PendingReview:
        """Interactive: pauses at human review and returns what the reviewer must answer."""
        thread, state, usage = self._invoke(app, interactive=True)
        if "__interrupt__" in state:
            self._pending_usage[thread] = usage
            return PendingReview(thread_id=thread, request=state["__interrupt__"][0].value,
                                 usage=usage)
        decision = state["decision"]
        decision.usage = usage
        return decision

    def resume(self, thread_id: str, review: HumanReview) -> UnderwritingDecision:
        from langgraph.types import Command
        with span("underwrite.resume", workflow__thread=thread_id,
                  review__decision=review.decision.value):
            state = self.graph.invoke(Command(resume=review.model_dump(mode="json")),
                                      self._config(thread_id))
        decision = state["decision"]
        decision.usage = self._pending_usage.pop(thread_id, None)
        return decision

    def assemble_case(self, app: LoanApplication) -> tuple[UnderwritingCase, list[AuditEvent]]:
        """Everything before the agent, run straight through (used by `prompt`)."""
        income, income_result = self.income_verifier.verify(app)
        case = self.build_case(app, income, income_result, self.run_checks(app))
        self.run_analyzers(case)
        case.analyses.append(self.policy_analyzer.analyze(case))
        return case, []
