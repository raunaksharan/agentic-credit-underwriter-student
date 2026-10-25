# Lesson 3 prompt pack: build the LLM agent with Claude Code

You build three modules in `src/underwriter/agents/` from `SPEC.md`. The LLM port, the
mock model, the prompt file and the tests are given.

```bash
cd ~/fde-work/lesson-03        # your copy of starter/lesson-03 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: context, validation, the agent
claude
```

The workflow tests are red too, because the workflow calls the agent. They go green
with step 4.

```text
/start-lesson 03
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 03
```

The plan goes context, then validators, then the agent loop, each with its tests.
Reject a plan that starts with the loop: you can't test it without the other two.

Then scaffold the interfaces (5 min). Test files import names from several of this
lesson's modules at the top, so until every name exists each file errors at import and
the per-step test commands below can't run. The scaffold makes each test fail on its own.
Skip it only if you'll write every module before running any test:

```text
<task>Scaffold the public API of lesson 03's modules</task>
<spec>lessons/03-structured-reasoning/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one (NotImplementedError) rather than at import, and
ruff is clean. No logic yet.</done_when>
```

## 2. Context (15 min)

```text
<task>Build src/underwriter/agents/context.py: CaseContext and build_context</task>
<spec>lessons/03-structured-reasoning/SPEC.md, section "context.py": payload keys, id formats, budget</spec>
<tests>uv run pytest tests/test_llm_agent.py -k context</tests>
<constraints>No name, date of birth, ID digits, email or address in the payload, ever. Keep
the id formats exactly: the validators and the prompt depend on them.</constraints>
<done_when>The context tests pass and ruff is clean.</done_when>
```

Then read what the model would see: `uv run underwriter prompt data/applications/APP-006.json`.
Is there any personal data in it? Ask Claude why policy excerpts are dropped first and
signals never.

## 3. Structured output and validators (20 min)

```text
<task>Build src/underwriter/agents/validation.py: UnderwritingOutput, parse_output, semantic_errors</task>
<spec>lessons/03-structured-reasoning/SPEC.md, section "validation.py" (the five checks and their exact messages)</spec>
<tests>uv run pytest tests/test_llm_agent.py -k "semantic or threshold or parse"</tests>
<constraints>Each message goes back to the model in the repair turn, so it must say exactly
what is wrong and what the fact is. Keep the tolerances as SPEC.md gives them.</constraints>
<done_when>Those tests pass and ruff is clean.</done_when>
```

## 4. The agent and the repair loop (20 min)

```text
<task>Build src/underwriter/agents/underwriting.py: build_messages and LLMUnderwritingAgent</task>
<spec>lessons/03-structured-reasoning/SPEC.md, section "underwriting.py"</spec>
<tests>uv run pytest tests/test_llm_agent.py -q, then uv run pytest and uv run underwriter run-all</tests>
<constraints>One answer plus one repair, then MANUAL_REVIEW. A provider outage is not
retried. The agent proposes; it never decides.</constraints>
<done_when>The whole suite is green and run-all shows 8/8.</done_when>
```

```bash
uv run underwriter run data/applications/APP-002.json --llm-fault malformed            # repaired
uv run underwriter run data/applications/APP-002.json --llm-fault wrong_number_always   # human
uv run underwriter run data/applications/APP-005.json --llm-fault malformed_always     # still DECLINE
```

If you kept your own Lesson 1 engine, make the change in SPEC.md › "Changes to earlier
modules" first.

## 5. Verify, review, learn (10 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest` and `run-all` (8/8) are green.
- The `prompt` output for every sample has no personal data in it.
- Your PR answers, in your own words: why does a persistent bad answer go to a human
  rather than to a third attempt?

## Don't delegate

The tolerances, what counts as personal data, and the explanation in your PR.
