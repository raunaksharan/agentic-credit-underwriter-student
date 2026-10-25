---
name: add-tool-check
description: Add a new external check (bureau, bank, identity or any API) as a typed tool with fault injection, a required/optional decision, tests and a golden case. Use when a request adds an integration or "calls" a new system.
---

# Add an external check

Every external call can time out, be rate-limited, fail or return garbage. The check
must say which, as data, and the decision must handle each case on purpose.

1. **Required or optional?** Ask if the request doesn't say. Required: a failure sends
   the case to review (`CHECK_UNAVAILABLE` or a specific code). Optional: a failure
   becomes an info signal and the decision continues. Write the choice and why in the
   docstring.
2. **The fake tool.** Add a function in `tools/checks.py` that reads synthetic data the
   way the real API would. It raises the `ToolError` subclasses in `tools/faults.py`
   (`ToolNoRecord`, `ToolTimeout`, …), never returns `None`.
3. **Register it.** Add a `CheckSpec(name, required, description, fn)` to `CHECKS`. If
   the payload has a schema, add a validator so a malformed answer becomes `INVALID`.
4. **Use the result.** Read it from `case.check("<name>")` in the analyzer that needs
   it. Branch on `status`, not on whether data happens to be present.
5. **Faults.** It must work with every kind: `timeout`, `rate_limit`, `server_error`,
   `malformed`, `latency:<ms>`. No new fault code paths inside the tool itself.
6. **Tests** (`tests/test_tools_and_agent.py` style): OK path, each fault kind → the
   right status, and the decision effect for required vs optional.
7. **Golden case.** Add one case per meaningful failure to `evals/golden_cases.json`
   under the `tools` tag, with a scenario sentence and the expected outcome from the
   policy. Then `uv run underwriter eval --update-baseline` and say why the metrics moved.
8. **Document.** A row in `architecture/failure-modes.md`.
9. **Verify.** `/verify`; a failure must never turn a DECLINE into an APPROVE.
