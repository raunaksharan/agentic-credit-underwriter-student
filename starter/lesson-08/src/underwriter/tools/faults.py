"""Fault injection for the fake tools.

Failures you can't reproduce, you can't test. A FaultPlan says which tool should
misbehave and how:

    TOOL_FAULTS="credit_bureau=timeout,bank_data=server_error"
    underwriter run APP-001.json --tool-fault credit_bureau=rate_limit

Kinds:  timeout · rate_limit (429) · server_error (500) · malformed · latency:<ms>
        flaky:<n> (lesson 8): a 500 on the first n calls, then normal answers

Fault injection is refused when APP_ENV=production.
"""

from __future__ import annotations

import os
import threading

KINDS = {"timeout", "rate_limit", "server_error", "malformed"}


class ToolError(Exception):
    """Base class: the tool did not produce a usable answer."""


class ToolTimeout(ToolError):
    pass


class ToolRateLimited(ToolError):
    def __init__(self, message: str, retry_after_s: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ToolServerError(ToolError):
    pass


class ToolNoRecord(ToolError):
    """The system of record has nothing for this applicant (not an outage)."""


class ToolMalformed(ToolError):
    """The tool answered, but the payload failed validation."""


class FaultPlan:
    def __init__(self, faults: dict[str, str] | None = None) -> None:
        self.faults = dict(faults or {})
        for tool, kind in self.faults.items():
            if kind not in KINDS and not kind.startswith(("latency:", "flaky:")):
                raise ValueError(f"unknown fault {kind!r} for {tool}; choose {sorted(KINDS)}, "
                                 "latency:<ms> or flaky:<n>")
        self._calls: dict[str, int] = {}
        self._lock = threading.Lock()
        if self.faults and os.environ.get("APP_ENV", "").lower() == "production":
            raise RuntimeError("fault injection is disabled when APP_ENV=production")

    @classmethod
    def parse(cls, spec: str | None) -> FaultPlan:
        if not spec:
            return cls()
        pairs = (item.split("=", 1) for item in spec.split(",") if item.strip())
        return cls({k.strip(): v.strip() for k, v in pairs})

    @classmethod
    def from_env(cls) -> FaultPlan:
        return cls.parse(os.environ.get("TOOL_FAULTS"))

    def for_tool(self, tool: str) -> str | None:
        return self.faults.get(tool)

    def latency_ms(self, tool: str) -> float:
        kind = self.faults.get(tool, "")
        return float(kind.split(":", 1)[1]) if kind.startswith("latency:") else 0.0

    def raise_if_faulted(self, tool: str) -> None:
        kind = self.faults.get(tool)
        if kind and kind.startswith("flaky:"):
            with self._lock:  # checks run in threads from lesson 8
                n = self._calls[tool] = self._calls.get(tool, 0) + 1
            if n <= int(kind.split(":", 1)[1]):
                raise ToolServerError(f"{tool}: 500 Internal Server Error (flaky, call {n})")
            return
        if kind == "timeout":
            raise ToolTimeout(f"{tool}: timed out")
        if kind == "rate_limit":
            raise ToolRateLimited(f"{tool}: 429 Too Many Requests", retry_after_s=2.0)
        if kind == "server_error":
            raise ToolServerError(f"{tool}: 500 Internal Server Error")
