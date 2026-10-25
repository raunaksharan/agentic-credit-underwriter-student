"""Per-node timeout, retry and failure policy for the workflow graph (lesson 5).

Every node in the graph runs through `run_node`, with its own NodePolicy:

    timeout_s     wall-clock budget for one attempt
    max_attempts  attempts in total (1 = no retry)
    on_failure    what the graph does when the last attempt fails:
                  "escalate"  stop and send the case to a human (WORKFLOW_ERROR)
                  "degrade"   carry on without this node's output, and say so
                  "fallback"  the node supplies a safe default itself

Only transient errors are retried: timeouts and TransientNodeError. A ValueError is
a bug, and retrying a bug only hides it.

Node faults rehearse each failure on demand (refused when APP_ENV=production):

    NODE_FAULTS="policy=error"        # raises a non-transient error
    NODE_FAULTS="income=transient"    # fails the first attempt only, retry succeeds
    NODE_FAULTS="analyze=hang"        # runs past its timeout

A timed-out attempt's thread can't be killed in Python; it finishes in the
background and its result is thrown away. Lesson 8 moves the I/O to asyncio, where
cancellation is real.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Literal, TypeVar

T = TypeVar("T")
NODE_FAULT_KINDS = {"error", "transient", "hang"}


class TransientNodeError(Exception):
    """A failure worth retrying: the next attempt may succeed."""


class NodeFailed(Exception):
    def __init__(self, node: str, attempts: int, reason: str) -> None:
        super().__init__(f"{node} failed after {attempts} attempt(s): {reason}")
        self.node, self.attempts, self.reason = node, attempts, reason


@dataclass(frozen=True)
class NodePolicy:
    timeout_s: float
    max_attempts: int = 1
    on_failure: Literal["escalate", "degrade", "fallback"] = "escalate"
    backoff_s: float = 0.05  # fixed and short here; lesson 8 adds exponential + jitter


@dataclass
class NodeRun:
    value: object
    attempts: int
    duration_ms: float
    errors: list[str]


class NodeFaults:
    def __init__(self, faults: dict[str, str] | None = None) -> None:
        self.faults = dict(faults or {})
        for node, kind in self.faults.items():
            if kind not in NODE_FAULT_KINDS:
                raise ValueError(f"unknown node fault {kind!r} for {node}; "
                                 f"choose {sorted(NODE_FAULT_KINDS)}")
        if self.faults and os.environ.get("APP_ENV", "").lower() == "production":
            raise RuntimeError("fault injection is disabled when APP_ENV=production")

    @classmethod
    def parse(cls, spec: str | None) -> NodeFaults:
        if not spec:
            return cls()
        pairs = (item.split("=", 1) for item in spec.split(",") if item.strip())
        return cls({k.strip(): v.strip() for k, v in pairs})

    @classmethod
    def from_env(cls) -> NodeFaults:
        return cls.parse(os.environ.get("NODE_FAULTS"))

    def apply(self, node: str, attempt: int, policy: NodePolicy) -> None:
        kind = self.faults.get(node)
        if kind == "error":
            raise RuntimeError(f"injected error in {node}")
        if kind == "transient" and attempt == 1:
            raise TransientNodeError(f"injected transient failure in {node}")
        if kind == "hang":
            time.sleep(policy.timeout_s * 1.5)


_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="node")


def run_node(name: str, fn: Callable[[], T], policy: NodePolicy,
             faults: NodeFaults | None = None) -> NodeRun:
    """Run fn under the policy. Returns a NodeRun or raises NodeFailed."""
    faults = faults or NodeFaults()
    errors: list[str] = []
    start = time.perf_counter()
    for attempt in range(1, policy.max_attempts + 1):
        def attempt_fn(attempt: int = attempt) -> T:
            faults.apply(name, attempt, policy)
            return fn()

        future = _pool.submit(attempt_fn)
        try:
            value = future.result(timeout=policy.timeout_s)
            return NodeRun(value, attempt, round((time.perf_counter() - start) * 1000, 1), errors)
        except FutureTimeout:
            errors.append(f"attempt {attempt}: timed out after {policy.timeout_s}s")
        except TransientNodeError as exc:
            errors.append(f"attempt {attempt}: {exc}")
        except Exception as exc:  # not transient: don't retry a bug
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            raise NodeFailed(name, attempt, errors[-1]) from exc
        if attempt < policy.max_attempts:
            time.sleep(policy.backoff_s)
    raise NodeFailed(name, policy.max_attempts, errors[-1])
