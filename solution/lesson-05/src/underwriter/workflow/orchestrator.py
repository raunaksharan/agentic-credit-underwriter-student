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
from underwriter.rag.analyzer import RetrievalPolicyAnalyzer
from underwriter.tools.checks import CHECKS, CheckSpec, run_checks
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

    # -- the steps the graph's nodes call --------------------------------------------

    def run_checks(self, app: LoanApplication) -> list[CheckResult]:
        return run_checks(app, self.faults, self.checks)

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

    def run(self, app: LoanApplication) -> UnderwritingDecision:
        """Non-interactive: escalated cases are queued and the run ends."""
        thread = f"{app.application_id}-{uuid.uuid4().hex[:8]}"
        state = self.graph.invoke({"application": app, "interactive": False, "audit": []},
                                  self._config(thread))
        return state["decision"]

    def start(self, app: LoanApplication) -> UnderwritingDecision | PendingReview:
        """Interactive: pauses at human review and returns what the reviewer must answer."""
        thread = f"{app.application_id}-{uuid.uuid4().hex[:8]}"
        state = self.graph.invoke({"application": app, "interactive": True, "audit": []},
                                  self._config(thread))
        if "__interrupt__" in state:
            return PendingReview(thread_id=thread, request=state["__interrupt__"][0].value)
        return state["decision"]

    def resume(self, thread_id: str, review: HumanReview) -> UnderwritingDecision:
        from langgraph.types import Command
        state = self.graph.invoke(Command(resume=review.model_dump(mode="json")),
                                  self._config(thread_id))
        return state["decision"]

    def assemble_case(self, app: LoanApplication) -> tuple[UnderwritingCase, list[AuditEvent]]:
        """Everything before the agent, run straight through (used by `prompt`)."""
        income, income_result = self.income_verifier.verify(app)
        case = self.build_case(app, income, income_result, self.run_checks(app))
        self.run_analyzers(case)
        case.analyses.append(self.policy_analyzer.analyze(case))
        return case, []
