"""The Credit Policy Intelligence Service: retrieval wired into the underwriting workflow.

Replaces lesson 1's StaticPolicyAnalyzer. For each fact or signal in the case it asks
the retriever for the governing text and attaches the citation as evidence. It never
changes the decision: thresholds stay in decision/policy.py (ADR-0002). Retrieval
explains and cites; the engine decides.
"""

from __future__ import annotations

from underwriter.domain.models import AnalysisResult, Evidence, ReasonCode, UnderwritingCase
from underwriter.rag.retriever import PolicyRetriever

POLICY = {"internal_policy"}
REGULATION = {"regulation"}


def _queries(case: UnderwritingCase) -> list[tuple[str, set[str]]]:
    m = case.metrics
    codes = {s.code for s in case.all_signals}
    q: list[tuple[str, set[str]]] = []
    if "credit_score" in m:
        q.append(("minimum credit score requirement", POLICY))
    if "post_loan_dti" in m:
        q.append((f"debt-to-income ratio {m['post_loan_dti']:.0%} after the requested loan",
                  POLICY))
    if m.get("income_discrepancy", 0) > 0:
        q.append(("stated income exceeds verified income", POLICY))
    if m.get("delinquencies_last_24m", 0) > 0:
        q.append(("delinquencies in the last 24 months", POLICY))
    if "loan_to_annual_income" in m:
        q.append(("requested loan amount limit relative to verified income", POLICY))
    if ReasonCode.CREDIT_DATA_UNAVAILABLE in codes:
        q.append(("no credit report available from the bureau", POLICY))
    if ReasonCode.MISSING_DOCUMENT in codes:
        q.append(("required income document missing tax return", POLICY))
    if codes & {ReasonCode.IDENTITY_MISMATCH, ReasonCode.FRAUD_SIGNAL}:
        q.append(("name on income documents does not match the applicant", POLICY))
        q.append(("identity theft red flags inconsistent personal identifying information",
                  REGULATION))
    if m.get("credit_score", 999) < 580 or m.get("delinquencies_last_24m", 0) >= 3:
        # a likely decline: the adverse action rules decide what the notice must say
        q.append(("adverse action notice statement of specific reasons", REGULATION))
    return q


class RetrievalPolicyAnalyzer:
    name = "policy_analysis"

    def __init__(self, retriever: PolicyRetriever | None = None) -> None:
        self.retriever = retriever or PolicyRetriever()

    def analyze(self, case: UnderwritingCase) -> AnalysisResult:
        r = AnalysisResult(service=self.name)
        seen: set[str] = set()
        for query, sources in _queries(case):
            res = self.retriever.retrieve(query, k=1, source_types=sources)
            if res.abstained or not res.results:
                continue
            top = res.results[0].chunk
            if top.chunk_id in seen:
                continue
            seen.add(top.chunk_id)
            r.evidence.append(Evidence(source=top.chunk_id,
                                       detail=f"{top.citation}: {top.text[:400]}"))
        return r
