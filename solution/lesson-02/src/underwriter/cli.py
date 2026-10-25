"""Command-line entry point.

    underwriter run data/applications/APP-002.json   # one application, full trace
    underwriter run-all                               # every sample vs expected outcome
    underwriter ingest                                # parse + chunk the corpus (L2)
    underwriter search "DTI 46%" [--as-of 2020-06-01] # hybrid retrieval (L2)
    underwriter eval-retrieval                        # retrieval eval (L2)
"""

from __future__ import annotations

import argparse
import json
import sys

from underwriter.domain.models import UnderwritingDecision
from underwriter.ingestion.documents import DATA_DIR, load_application
from underwriter.workflow.orchestrator import UnderwritingWorkflow


def _print_decision(d: UnderwritingDecision) -> None:
    print(f"\n=== {d.application_id}: {d.recommendation.value} ===")
    print(f"Reasons:  {', '.join(r.value for r in d.reason_codes)}")
    print(f"Agent proposed {d.agent_recommendation.recommendation.value}"
          + ("; overridden by policy" if d.overridden_by_policy else ""))
    if d.agent_recommendation.missing_information:
        print("Missing:  " + "; ".join(d.agent_recommendation.missing_information))
    print("Metrics:  " + ", ".join(f"{k}={v}" for k, v in sorted(d.metrics.items())))
    print("Trace:")
    for e in d.audit_trail:
        print(f"  [{e.step:<19}] {e.actor:<26} {e.summary}")


def cmd_run(path: str, as_json: bool) -> int:
    decision = UnderwritingWorkflow().run(load_application(path))
    if as_json:
        print(decision.model_dump_json(indent=2))
    else:
        _print_decision(decision)
    return 0


def cmd_run_all() -> int:
    expected = json.loads((DATA_DIR / "expected_outcomes.json").read_text())
    workflow = UnderwritingWorkflow()
    failures = 0
    print(f"{'Application':<12} {'Expected':<14} {'Actual':<14} Reasons")
    for app_id, spec in expected.items():
        d = workflow.run(load_application(DATA_DIR / "applications" / f"{app_id}.json"))
        ok = d.recommendation.value == spec["expected"]
        failures += not ok
        mark = "ok  " if ok else "FAIL"
        print(f"{app_id:<12} {spec['expected']:<14} {d.recommendation.value:<14} "
              f"{mark} {', '.join(r.value for r in d.reason_codes)}")
    print(f"\n{len(expected) - failures}/{len(expected)} match expected outcomes")
    return 1 if failures else 0


def cmd_ingest() -> int:
    from underwriter.rag.retriever import default_index
    idx = default_index()
    print(f"{'Document':<28} {'Status':<11} Chunks")
    for doc_id, n in idx.stats().items():
        print(f"{doc_id:<28} {idx.docs[doc_id].status:<11} {n}")
    print(f"\n{len(idx.chunks)} chunks from {len(idx.docs)} documents "
          f"(embedder: {idx.embedder.name})")
    return 0


def cmd_search(query: str, k: int, as_of: str | None, include_withdrawn: bool) -> int:
    from datetime import date

    from underwriter.rag.retriever import PolicyRetriever
    res = PolicyRetriever().retrieve(query, k=k, include_withdrawn=include_withdrawn,
                                     as_of=date.fromisoformat(as_of) if as_of else None)
    print(f"Query: {query}  (as of {res.as_of})")
    if res.abstained:
        print(res.reason)
        return 0
    for i, r in enumerate(res.results, 1):
        c = r.chunk
        flag = "" if c.status == "current" else f"  [{c.status.upper()}]"
        print(f"\n{i}. {c.citation}{flag}\n   id: {c.chunk_id}\n   rrf {r.score:.4f} · "
              f"bm25 rank {r.bm25_rank or '-'} · vector rank {r.vector_rank or '-'}\n"
              f"   {c.text[:240]}…")
    return 0


def cmd_eval_retrieval() -> int:
    from underwriter.evaluation.retrieval import print_report, run_retrieval_eval
    report = run_retrieval_eval()
    print_report(report)
    return 0 if report.passed == len(report.cases) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="underwriter")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Underwrite one application")
    run.add_argument("path")
    run.add_argument("--json", action="store_true", help="Print the full decision as JSON")
    sub.add_parser("run-all", help="Run every sample application against expected outcomes")
    sub.add_parser("ingest", help="Parse and chunk the policy corpus; show counts")
    search = sub.add_parser("search", help="Search the policy corpus")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)
    search.add_argument("--as-of", help="YYYY-MM-DD: retrieve what was in force on this date")
    search.add_argument("--include-withdrawn", action="store_true",
                        help="Research mode: also show withdrawn or superseded documents")
    sub.add_parser("eval-retrieval", help="Run the lesson 2 retrieval eval")
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args.path, args.json)
    if args.command == "ingest":
        return cmd_ingest()
    if args.command == "search":
        return cmd_search(args.query, args.k, args.as_of, args.include_withdrawn)
    if args.command == "eval-retrieval":
        return cmd_eval_retrieval()
    return cmd_run_all()


if __name__ == "__main__":
    sys.exit(main())
