"""Tools the underwriting agent may call (lesson 4).

The allow-list is the security boundary. The agent can look things up and ask for
documents; it cannot approve, decline, change data or call anything not listed here.
Each tool validates its arguments and returns a small JSON result with citable ids.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from underwriter.domain.models import DocumentType, UnderwritingCase
from underwriter.rag.retriever import PolicyRetriever


class CheckPolicyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=3, max_length=300)


class RequestDocumentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_type: DocumentType
    reason: str = Field(min_length=3, max_length=300)


class CheckResultArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str


@dataclass
class AgentTool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[BaseModel], dict]

    def schema_line(self) -> str:
        props = self.args.model_json_schema().get("properties", {})
        params = ", ".join(f"{k}: {v.get('type', 'string')}" for k, v in props.items())
        return f"- {self.name}({params}): {self.description}"


@dataclass
class ToolBox:
    """The tools for one case, plus everything they produced (for citations and audit)."""

    tools: dict[str, AgentTool]
    new_ids: dict[str, str] = field(default_factory=dict)
    requested_documents: list[dict] = field(default_factory=list)

    def describe(self) -> str:
        return "\n".join(t.schema_line() for t in self.tools.values())

    def call(self, name: str, arguments: dict) -> tuple[bool, dict]:
        """Returns (ok, result). Unknown tools and bad arguments are errors, not crashes."""
        tool = self.tools.get(name)
        if tool is None:
            return False, {"error": f"tool '{name}' is not allowed; allowed: {sorted(self.tools)}"}
        try:
            args = tool.args.model_validate(arguments)
        except ValidationError as exc:
            return False, {"error": f"bad arguments for {name}: {exc.error_count()} errors",
                           "details": json.loads(exc.json(include_url=False))[:3]}
        return True, tool.fn(args)


def build_toolbox(case: UnderwritingCase, retriever: PolicyRetriever) -> ToolBox:
    box = ToolBox(tools={})

    def check_policy(args: CheckPolicyArgs) -> dict:
        res = retriever.retrieve(args.query, k=3)
        if res.abstained:
            return {"abstained": True, "reason": res.reason}
        out = []
        for r in res.results:
            box.new_ids[r.chunk.chunk_id] = r.chunk.citation
            out.append({"id": r.chunk.chunk_id, "citation": r.chunk.citation,
                        "excerpt": r.chunk.text[:300]})
        return {"results": out}

    def request_missing_document(args: RequestDocumentArgs) -> dict:
        req_id = f"request:{args.doc_type.value}"
        box.requested_documents.append({"doc_type": args.doc_type.value, "reason": args.reason})
        box.new_ids[req_id] = f"Requested {args.doc_type.value}: {args.reason}"
        return {"id": req_id, "status": "queued for the applicant"}

    def get_check_result(args: CheckResultArgs) -> dict:
        c = case.check(args.tool)
        if c is None:
            return {"error": f"no check named {args.tool}",
                    "available": [x.tool for x in case.checks]}
        cid = f"check:{c.tool}"
        box.new_ids[cid] = f"{c.tool} {c.status.value}"
        return {"id": cid, "status": c.status.value, "reason": c.reason, "data": c.data}

    box.tools = {
        "check_policy": AgentTool("check_policy",
                                  "search lending policy and regulation; returns cited excerpts",
                                  CheckPolicyArgs, check_policy),
        "request_missing_document": AgentTool(
            "request_missing_document", "ask the applicant for a document (payslip, "
            "bank_statement, tax_return, employment_letter, id_proof)",
            RequestDocumentArgs, request_missing_document),
        "get_check_result": AgentTool("get_check_result",
                                      "read the result of an external check already run",
                                      CheckResultArgs, get_check_result),
    }
    return box
