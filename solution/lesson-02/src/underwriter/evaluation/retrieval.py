"""Retrieval eval: hit@5, MRR, abstain accuracy and stale citations.

    uv run underwriter eval-retrieval
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from underwriter.rag.models import Chunk
from underwriter.rag.retriever import PolicyRetriever, in_force

CASES = Path(__file__).resolve().parents[3] / "evals" / "retrieval_cases.json"


class CaseResult(BaseModel):
    id: str
    query: str
    must_abstain: bool
    abstained: bool
    rank: int | None  # 1-based rank of the first matching result
    stale: int  # results not in force on the query date (default mode only)
    top: list[str]

    @property
    def passed(self) -> bool:
        if self.must_abstain:
            return self.abstained
        return not self.abstained and self.rank is not None and self.stale == 0


class RetrievalReport(BaseModel):
    cases: list[CaseResult]

    def _answerable(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.must_abstain]

    @property
    def hit_at_5(self) -> float:
        a = self._answerable()
        return sum(c.rank is not None for c in a) / len(a)

    @property
    def mrr(self) -> float:
        a = self._answerable()
        return sum(1 / c.rank for c in a if c.rank) / len(a)

    @property
    def abstain_accuracy(self) -> float:
        return sum(c.abstained == c.must_abstain for c in self.cases) / len(self.cases)

    @property
    def stale_citations(self) -> int:
        return sum(c.stale for c in self.cases)

    @property
    def passed(self) -> int:
        return sum(c.passed for c in self.cases)


def _matches(chunk: Chunk, exp: dict) -> bool:
    if chunk.doc_id != exp["doc_id"]:
        return False
    if "section" in exp and chunk.section_id != exp["section"]:
        return False
    if "section_contains" in exp and exp["section_contains"] not in chunk.section_id:
        return False
    if "label" in exp and not chunk.first_label.startswith(exp["label"]):
        return False
    return True


def run_retrieval_eval(retriever: PolicyRetriever | None = None,
                       cases_path: Path = CASES) -> RetrievalReport:
    retriever = retriever or PolicyRetriever()
    docs = retriever.index.docs
    out = []
    for case in json.loads(cases_path.read_text())["cases"]:
        as_of = date.fromisoformat(case["as_of"]) if "as_of" in case else None
        include_withdrawn = case.get("include_withdrawn", False)
        res = retriever.retrieve(case["query"], k=5, as_of=as_of,
                                 include_withdrawn=include_withdrawn)
        rank = None
        for i, r in enumerate(res.results, 1):
            if any(_matches(r.chunk, e) for e in case.get("expect", [])):
                rank = i
                break
        stale = 0 if include_withdrawn else sum(
            not in_force(docs[r.chunk.doc_id], docs, res.as_of) for r in res.results)
        out.append(CaseResult(id=case["id"], query=case["query"],
                              must_abstain=case.get("must_abstain", False),
                              abstained=res.abstained, rank=rank, stale=stale,
                              top=[r.chunk.citation for r in res.results[:3]]))
    return RetrievalReport(cases=out)


def print_report(report: RetrievalReport) -> None:
    print(f"{'Case':<5} {'Result':<7} {'Rank':<5} {'Abst':<5} Top result")
    for c in report.cases:
        print(f"{c.id:<5} {'pass' if c.passed else 'FAIL':<7} {str(c.rank or '-'):<5} "
              f"{'yes' if c.abstained else 'no':<5} {(c.top[0] if c.top else '(abstained)')[:70]}")
    print(f"\nhit@5 {report.hit_at_5:.2f} · MRR {report.mrr:.2f} · "
          f"abstain accuracy {report.abstain_accuracy:.2f} · stale citations "
          f"{report.stale_citations} · {report.passed}/{len(report.cases)} cases pass")
