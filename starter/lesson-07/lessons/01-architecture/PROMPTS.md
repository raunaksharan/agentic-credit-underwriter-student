# Lesson 1 prompt pack: build the calculations and the decision engine with Claude Code

You build two modules from `SPEC.md` (in this folder). The tests are the answer key.
The loop behind every step is in `workflows/build-a-module-with-claude.md`.

```bash
cd ~/fde-work/lesson-01        # your copy of starter/lesson-01 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: both modules are empty
claude                                               # trust the folder when asked
```

```text
/start-lesson 01
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 01
```

Check the plan before approving it:
- It builds `calculations.py` first, then `engine.py`.
- It names `tests/test_calculations.py` and `tests/test_decision_engine.py`.
- It touches neither `decision/policy.py` nor `tests/`.

If it asks something CLAUDE.md › Clarifications already answers, point it there.

Then scaffold the interfaces (5 min). Test files import names from several of this
lesson's modules at the top, so until every name exists each file errors at import and
the per-step test commands below can't run. The scaffold makes each test fail on its own.
Skip it only if you'll write every module before running any test:

```text
<task>Scaffold the public API of lesson 01's modules</task>
<spec>lessons/01-architecture/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one (NotImplementedError) rather than at import, and
ruff is clean. No logic yet.</done_when>
```

## 2. The calculations (15 min)

```text
<task>Build src/underwriter/risk/calculations.py</task>
<spec>lessons/01-architecture/SPEC.md, section "risk/calculations.py", and the Public API section</spec>
<tests>uv run pytest tests/test_calculations.py</tests>
<constraints>Pure functions, exact arithmetic, no rounding inside, ValueError on the inputs
SPEC.md lists. No new dependency. Don't edit tests/.</constraints>
<done_when>The tests pass and ruff is clean. Show me the diff.</done_when>
```

Ask Claude:
- What does `monthly_payment` return for a 0% loan, and why?
- Why does DTI use gross income, not net?

Check its answers against CLAUDE.md › Clarifications.

## 3. The decision engine (30 min)

```text
<task>Build src/underwriter/decision/engine.py: PolicyFinding, EngineResult, DecisionEngine</task>
<spec>lessons/01-architecture/SPEC.md, section "decision/engine.py" (the rules table and decide)</spec>
<context>ADR-0002 in architecture/adr/: the agent may escalate but never relax policy; an
agent DECLINE outside policy becomes MANUAL_REVIEW. Thresholds come only from
PolicyThresholds; every finding cites its policy section.</context>
<tests>uv run pytest tests/test_decision_engine.py -q, then uv run pytest and uv run underwriter run-all</tests>
<constraints>Don't edit tests/ or decision/policy.py. A missing metric fires no rule (the
analyzers already raised a review signal); never default it to 0.</constraints>
<done_when>All tests pass and run-all shows 8/8.</done_when>
```

Then run `uv run underwriter run data/applications/APP-008.json` and find the override.

## 4. Verify, review, learn (10 min)

```text
/verify
/review
```

Accept or reject each finding, with a reason. For each one that would apply again:

```text
/learn <what went wrong, in a few words>
```

## Stretch, or homework: a new policy rule (40 min)

```text
<task>Add a policy rule using the add-policy-rule skill</task>
<rule>Policy §2.1: applicants must be at least 21 on the application date.</rule>
<constraints>Ask me anything the policy doesn't say before you start.</constraints>
```

Expect it to ask which analyzer computes age, and what happens when the date of birth
is missing. Answer those yourself; they're the design decisions this lesson is about.

## Done when

- `uv run pytest` is green and `uv run underwriter run-all` shows 8/8 (9/9 with the
  stretch).
- Your PR has the plan (`docs/plans/`), the rejected review findings with your reasons,
  any CLAUDE.md learning lines, and a paragraph you wrote covering:
  - the 0% loan;
  - gross vs net income;
  - why an agent DECLINE outside policy goes to a human.

## Don't delegate

The threshold values, the expected outcome of any new sample, and the "why it works"
paragraph.
