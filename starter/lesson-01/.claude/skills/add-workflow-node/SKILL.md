---
name: add-workflow-node
description: Add a step to the LangGraph underwriting workflow with its own timeout, retry and failure policy (escalate, degrade or fallback), audit events, a node fault and tests. Use when a new stage joins the workflow (from lesson 5).
---

# Add a workflow node

Every node fails sometimes. Decide what the decision does when this one fails before
writing it.

1. **Decide the failure policy** (`clarify-before-building` if the request doesn't say):
   - `escalate`: required; the case goes to a human with WORKFLOW_ERROR.
   - `degrade`: carry on without its output, and say so in the audit.
   - `fallback`: the node supplies a safe default itself.

   Also decide the timeout, and whether its errors are transient (worth a retry).
2. **Write the node** in `workflow/graph.py` as a small function that calls a component
   (not business logic inline), wrapped in `guarded(name, fn, state, on_ok)`. It
   returns only its new state keys and its new audit events; `audit` is append-only.
3. **Policy:** add a `NodePolicy(timeout_s=…, max_attempts=…, on_failure=…)` entry to
   `NODE_POLICIES`.
4. **Edges:** add it with `g.add_node`, plus a `next_or_escalate` edge if it can
   escalate. Update `tests/test_workflow_graph.py::test_graph_has_the_designed_shape`
   only with the instructor's agreement, since it is the agreed design.
5. **Faults:** it must work with `NODE_FAULTS="<name>=error|transient|hang"`. Write a test
   for each, showing the policy's effect on the decision and the audit.
6. **Trace (lesson 7 on):** `guarded` gives it a span; add useful attributes, never
   personal data.
7. **Document:** a row in `architecture/failure-modes.md`; then `/verify`, and
   `uv run underwriter graph` to see it in the diagram.
