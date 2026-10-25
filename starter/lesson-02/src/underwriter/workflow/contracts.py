"""Service contracts: the boundaries drawn in the lesson 1 architecture.

Each protocol is tagged with who implements it over the course:

    DETERMINISTIC  code only, unit-tested, never an LLM
    AI             LLM-backed from the lesson noted; a rules stub until then
    HUMAN          a person, reached through a queue

Swapping a stub for an LLM implementation must not change any other module.
That is the test of a good boundary.
"""

from __future__ import annotations

from typing import Protocol

from underwriter.domain.models import (
    AgentRecommendation,
    AnalysisResult,
    LoanApplication,
    UnderwritingCase,
    UnderwritingDecision,
    VerifiedIncome,
)


class IncomeVerifier(Protocol):
    """DETERMINISTIC rules over AI-extracted documents (LLM extraction: lesson 3)."""

    def verify(self, app: LoanApplication) -> tuple[VerifiedIncome, AnalysisResult]: ...


class Analyzer(Protocol):
    """One branch of the parallel fan-out (concurrency: lesson 8).

    Credit, financial and fraud analyzers are DETERMINISTIC.
    The policy analyzer becomes retrieval-backed (RAG: lesson 2).
    """

    name: str

    def analyze(self, case: UnderwritingCase) -> AnalysisResult: ...


class UnderwritingAgent(Protocol):
    """AI from lesson 3 (structured output), with tools in lesson 4 and a workflow in
    lesson 5. Proposes; does not decide."""

    def recommend(self, case: UnderwritingCase) -> AgentRecommendation: ...


class ReviewQueue(Protocol):
    """HUMAN. Receives every case the decision engine escalates."""

    def submit(self, decision: UnderwritingDecision) -> str: ...
