"""Command-line entry point.

    underwriter run data/applications/APP-002.json   # one application, full trace
    underwriter run-all                               # every sample vs expected outcome
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="underwriter")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Underwrite one application")
    run.add_argument("path")
    run.add_argument("--json", action="store_true", help="Print the full decision as JSON")
    sub.add_parser("run-all", help="Run every sample application against expected outcomes")
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args.path, args.json)
    return cmd_run_all()


if __name__ == "__main__":
    sys.exit(main())
