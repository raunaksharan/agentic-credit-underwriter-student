"""Command-line entry point.

    underwriter run data/applications/APP-002.json   # one application, full trace
    underwriter run-all                               # every sample vs expected outcome
    underwriter ingest                                # parse + chunk the corpus (L2)
    underwriter search "DTI 46%" [--as-of 2020-06-01] # hybrid retrieval (L2)
    underwriter eval-retrieval                        # retrieval eval (L2)
    underwriter check-llm                             # ping the configured LLM (L3)
    underwriter prompt data/applications/APP-002.json # what the model sees (L3)
    underwriter run APP-002.json --llm-fault malformed  # rehearse a model failure (L3)
    underwriter run APP-001.json --tool-fault credit_bureau=timeout   # tool failure (L4)
    underwriter run APP-003.json --agent single         # lesson 3 agent, no tools (L4)
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
    p = d.agent_recommendation
    print(f"Model:    {p.model} · prompt {p.prompt_version} · attempts {p.attempts} · "
          f"tokens {p.input_tokens} in / {p.output_tokens} out"
          + ("" if p.valid else f" · INVALID: {'; '.join(p.validation_errors[:2])}"))
    for c in p.tool_calls:
        print(f"Tool:     {c['tool']}({json.dumps(c['arguments'])}) -> {c['outcome']}"
              + (f": {c['detail']}" if c["detail"] else ""))
    if d.agent_recommendation.missing_information:
        print("Missing:  " + "; ".join(d.agent_recommendation.missing_information))
    print("Metrics:  " + ", ".join(f"{k}={v}" for k, v in sorted(d.metrics.items())))
    print("Trace:")
    for e in d.audit_trail:
        print(f"  [{e.step:<19}] {e.actor:<26} {e.summary}")


def _workflow(llm_fault: str | None = None, tool_fault: str | None = None,
              agent: str | None = None) -> UnderwritingWorkflow:
    from underwriter.agents.factory import get_agent
    from underwriter.tools.faults import FaultPlan
    faults = FaultPlan.parse(tool_fault) if tool_fault else None
    return UnderwritingWorkflow(agent=get_agent(agent, llm_fault), faults=faults)


def cmd_run(path: str, as_json: bool, llm_fault: str | None = None,
            tool_fault: str | None = None, agent: str | None = None) -> int:
    decision = _workflow(llm_fault, tool_fault, agent).run(load_application(path))
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


def cmd_check_llm() -> int:
    from underwriter.llm.client import LLMUnavailable, Message
    from underwriter.llm.config import get_llm_client
    try:
        client = get_llm_client()
        ping = Message(role="user", content='Reply with the JSON {"reply": "ok"}')
        resp = client.complete([ping], max_output_tokens=20, json_mode=True)
    except LLMUnavailable as exc:
        print(f"LLM unavailable: {exc}")
        return 1
    print(f"model {resp.model} · {resp.input_tokens} tokens in / {resp.output_tokens} out · "
          f"{resp.latency_ms:.0f} ms\nreply: {resp.text.strip()[:200]}")
    return 0


def cmd_prompt(path: str) -> int:
    """Print exactly what the model would see for this application."""
    from underwriter.agents.underwriting import build_messages
    case, _ = UnderwritingWorkflow().assemble_case(load_application(path))
    messages, ctx = build_messages(case)
    for m in messages:
        print(f"===== {m.role} =====\n{m.content}\n")
    print(f"[context: {len(ctx.as_json)} chars, {len(ctx.allowed_ids)} citable ids, "
          f"{ctx.dropped_policy} policy excerpts dropped for budget]")
    return 0


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
    run.add_argument("--llm-fault", help="Mock LLM fault: malformed, bad_citation, wrong_number, "
                     "unavailable, *_always (lesson 3), loop, disallowed_tool (lesson 4)")
    run.add_argument("--tool-fault", help="e.g. credit_bureau=timeout,bank_data=server_error "
                     "(kinds: timeout, rate_limit, server_error, malformed, latency:<ms>)")
    run.add_argument("--agent", choices=["tools", "single"],
                     help="tools: bounded tool-calling agent (default); single: lesson 3")
    sub.add_parser("check-llm", help="One tiny call to the configured LLM (lesson 3)")
    prompt = sub.add_parser("prompt", help="Show the exact prompt for an application (lesson 3)")
    prompt.add_argument("path")
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
        return cmd_run(args.path, args.json, args.llm_fault, args.tool_fault, args.agent)
    if args.command == "check-llm":
        return cmd_check_llm()
    if args.command == "prompt":
        return cmd_prompt(args.path)
    if args.command == "ingest":
        return cmd_ingest()
    if args.command == "search":
        return cmd_search(args.query, args.k, args.as_of, args.include_withdrawn)
    if args.command == "eval-retrieval":
        return cmd_eval_retrieval()
    return cmd_run_all()


if __name__ == "__main__":
    sys.exit(main())
