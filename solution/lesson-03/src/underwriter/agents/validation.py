"""Structured output and semantic validation.

A JSON object that parses is not the same as an answer you can use. Schema checks
catch shape; these checks catch content:

- every cited id exists in the context the model was given
- every number in "figures" equals the fact it claims to copy
- every percentage written in the rationale matches a known ratio
- missing information or open review signals cannot come with an APPROVE
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from underwriter.agents.context import RATIO_METRICS, CaseContext

RATIO_TOLERANCE = 0.0005  # fractions: 0.4559 vs 0.4561 is fine; 0.35 vs 0.4559 is not
PERCENT_TOLERANCE = 0.15  # percentage points, for numbers written in prose


class UnderwritingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: Literal["APPROVE", "DECLINE", "MANUAL_REVIEW"]
    rationale: str = Field(max_length=800)
    risk_factors: list[str] = []
    missing_information: list[str] = []
    evidence: list[str] = Field(min_length=1)
    figures: dict[str, float] = {}


def parse_output(text: str) -> UnderwritingOutput:
    """Parse model text into the schema, tolerating code fences and chatter."""
    cleaned = re.sub(r"```(?:json)?", "", text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the reply")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"reply is not valid JSON: {exc.msg}") from exc
    try:
        return UnderwritingOutput.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise ValueError(f"reply does not match the schema: {problems}") from exc


def semantic_errors(out: UnderwritingOutput, ctx: CaseContext) -> list[str]:
    errors: list[str] = []
    metrics = ctx.payload["metrics"]

    unknown = [e for e in out.evidence if e not in ctx.allowed_ids]
    if unknown:
        errors.append(f"evidence cites ids not in the context: {unknown}")

    for name, value in out.figures.items():
        if name not in metrics:
            errors.append(f"figures.{name} is not a metric in the context")
            continue
        actual = metrics[name]["value"]
        tol = RATIO_TOLERANCE if name in RATIO_METRICS else 0.5
        if abs(value - actual) > tol:
            errors.append(f"figures.{name} = {value} but the fact is {actual}")

    ratios = [metrics[n]["value"] * 100 for n in RATIO_METRICS if n in metrics]
    # percentages that appear in the policy excerpts (e.g. "above 43%") may be quoted too
    quoted = {float(x) for p in ctx.payload["policy"]
              for x in re.findall(r"(\d+(?:\.\d+)?)\s*%", p["excerpt"])}
    for pct in re.findall(r"(\d+(?:\.\d+)?)\s*%", out.rationale):
        p = float(pct)
        if p in quoted:
            continue
        if not any(abs(p - r) <= PERCENT_TOLERANCE for r in ratios):
            errors.append(f"rationale states {pct}% which matches no fact in the context")

    if out.missing_information and out.recommendation != "MANUAL_REVIEW":
        errors.append("information is missing but the recommendation is not MANUAL_REVIEW")
    open_review = [s["code"] for s in ctx.payload["signals"] if s["severity"] == "review"]
    if open_review and out.recommendation == "APPROVE":
        errors.append(f"APPROVE despite open review signals: {open_review}")
    return errors
