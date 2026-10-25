# Lesson 4 prompt pack: build typed checks and a bounded tool agent with Claude Code

You build three modules from `SPEC.md`. The fault plan, the mock model's tool mode,
the prompt and the tests are given.

```bash
cd ~/fde-work/lesson-04        # your copy of starter/lesson-04 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: checks, tools, the agent loop
claude
```

```text
/start-lesson 04
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 04
```

Bottom-up again: the typed checks, then the allow-list, then the loop. Ask the plan to
name the failure mode each step closes (the F-numbers in
`architecture/failure-modes.md`).

Then scaffold the interfaces (5 min). Test files import names from several of this
lesson's modules at the top, so until every name exists each file errors at import and
the per-step test commands below can't run. The scaffold makes each test fail on its own.
Skip it only if you'll write every module before running any test:

```text
<task>Scaffold the public API of lesson 04's modules</task>
<spec>lessons/04-tool-agents/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one (NotImplementedError) rather than at import, and
ruff is clean. No logic yet.</done_when>
```

## 2. Typed checks (20 min)

```text
<task>Build src/underwriter/tools/checks.py: CheckSpec, the four fake tools, CHECKS,
run_check, run_checks</task>
<spec>lessons/04-tool-agents/SPEC.md, section "tools/checks.py" (the tools table and the
exception-to-status table)</spec>
<tests>uv run pytest tests/test_tools_and_agent.py -k "typed or faults_map or no_bureau"</tests>
<constraints>Every outcome is a CheckResult: nothing raises and nothing returns None. A
malformed answer is INVALID, never OK. No bureau message passes through: it can contain ID
digits.</constraints>
<done_when>Those tests pass and ruff is clean.</done_when>
```

Ask Claude why a malformed answer is INVALID and not OK. Check its answer against the
validator and the engine. The end-to-end fault tests stay red until step 4: they run the
whole workflow, which needs the agent.

## 3. The allow-list (15 min)

```text
<task>Build src/underwriter/agents/tools.py: the argument models, AgentTool, ToolBox,
build_toolbox</task>
<spec>lessons/04-tool-agents/SPEC.md, section "agents/tools.py"</spec>
<tests>uv run pytest tests/test_tools_and_agent.py -k toolbox</tests>
<constraints>A refused call is a tool result for the model, not an exception. No tool
decides, approves or changes data.</constraints>
<done_when>The toolbox test passes and ruff is clean.</done_when>
```

## 4. The bounded loop (25 min)

```text
<task>Build src/underwriter/agents/tool_agent.py: parse_action and ToolUsingUnderwritingAgent</task>
<spec>lessons/04-tool-agents/SPEC.md, section "agents/tool_agent.py" (the five-step loop)</spec>
<tests>uv run pytest tests/test_tools_and_agent.py -q, then uv run pytest and uv run underwriter run-all</tests>
<constraints>Deadline, tool-call cap, one repair, then MANUAL_REVIEW with a reason code. Use
the injected clock, never time.time(). Tool results are citable through box.new_ids.</constraints>
<done_when>The whole suite is green and run-all shows 8/8.</done_when>
```

Then run the whole workflow under faults and read each line:

```bash
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=timeout    # review
uv run underwriter run data/applications/APP-001.json --tool-fault credit_bureau=malformed  # review
uv run underwriter run data/applications/APP-001.json --tool-fault bank_data=server_error   # APPROVE
uv run underwriter run data/applications/APP-007.json                          # requests tax_return
uv run underwriter run data/applications/APP-001.json --llm-fault loop          # cut off at 4 calls
uv run underwriter run data/applications/APP-001.json --llm-fault disallowed_tool  # refused, recovers
```

Why does a bank-data outage still approve? Check against `CHECKS`: which checks are
required?

## 5. Verify, review, learn (10 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest` and `run-all` (8/8) are green.
- The looping agent stops at 4 tool calls with `AGENT_LIMIT_REACHED`.
- Your PR answers: what stops this agent from approving a loan on its own? Name the
  lines of code, not the prompt.

## Don't delegate

Which checks are required, and the limits (`MAX_TOOL_CALLS`, the deadline). Write down
why before anyone tunes them.
