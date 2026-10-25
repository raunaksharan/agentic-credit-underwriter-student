"""Print finished spans as a tree: `underwriter trace <application>` (lesson 7)."""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

# the attributes worth seeing at a glance, in display order
SHOWN = ("node.outcome", "node.attempts", "check.status", "check.required", "check.reason",
         "retrieval.results", "retrieval.abstained", "gen_ai.usage.input_tokens",
         "gen_ai.usage.output_tokens", "tool.outcome", "decision.recommendation",
         "decision.reason_codes", "llm.cost_usd")
SHORT = {"gen_ai.usage.input_tokens": "in", "gen_ai.usage.output_tokens": "out",
         "decision.recommendation": "decision", "decision.reason_codes": "reasons"}


def _ms(s: ReadableSpan) -> float:
    return (s.end_time - s.start_time) / 1e6


def render_tree(spans: Sequence[ReadableSpan]) -> str:
    children: dict[int | None, list[ReadableSpan]] = {}
    for s in spans:
        parent = s.parent.span_id if s.parent else None
        children.setdefault(parent, []).append(s)
    for v in children.values():
        v.sort(key=lambda s: s.start_time)
    lines: list[str] = []

    def walk(s: ReadableSpan, prefix: str, last: bool, root: bool) -> None:
        attrs = []
        for key in SHOWN:
            if key in s.attributes:
                v = s.attributes[key]
                v = ",".join(v) if isinstance(v, tuple) else v
                attrs.append(f"{SHORT.get(key, key.split('.')[-1])}={v}")
        flag = "  ✗" if s.status.status_code == StatusCode.ERROR else ""
        branch = "" if root else ("└─ " if last else "├─ ")
        lines.append(f"{prefix}{branch}{s.name:<{max(1, 40 - len(prefix) - len(branch))}} "
                     f"{_ms(s):7.1f} ms  {' '.join(attrs)}{flag}")
        kids = children.get(s.context.span_id, [])
        for i, k in enumerate(kids):
            walk(k, prefix + ("" if root else ("   " if last else "│  ")), i == len(kids) - 1,
                 False)

    for r in children.get(None, []):
        walk(r, "", True, True)
    return "\n".join(lines)
