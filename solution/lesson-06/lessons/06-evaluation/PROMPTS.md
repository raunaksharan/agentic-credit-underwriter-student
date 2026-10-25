# Lesson 6 prompt pack: build the eval harness (take-home)

This lesson is written to be done on your own, after Lesson 5, in about two hours. Read
the lesson guide first, then build the one module in `SPEC.md` with Claude Code.

The 32 golden cases (`evals/golden_cases.json`), the gates and the baseline are given.
They are the spec: their expected answers come from reading the policy, so don't edit
them to make a run pass.

```bash
cd ~/fde-work/lesson-06        # your copy of starter/lesson-06 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: tests/test_eval_harness.py
claude
```

```text
/start-lesson 06
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 06
```

Ask Claude to explain the difference between an expectation (what one case expects) and
an invariant (what every case must satisfy). Plan the invariants first.

Then scaffold the interfaces (5 min). Test files import names from several of this
lesson's modules at the top, so until every name exists each file errors at import and
the per-step test commands below can't run. The scaffold makes each test fail on its own.
Skip it only if you'll write every module before running any test:

```text
<task>Scaffold the public API of lesson 06's modules</task>
<spec>lessons/06-evaluation/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one (NotImplementedError) rather than at import, and
ruff is clean. No logic yet.</done_when>
```

## 2. Models, invariants and expectations (40 min)

```text
<task>In src/underwriter/evaluation/harness.py build the paths, Expect, GoldenCase,
CaseOutcome, invariant_violations, expectation_failures, load_cases and run_case</task>
<spec>lessons/06-evaluation/SPEC.md, section "evaluation/harness.py": models, invariants, expectations</spec>
<tests>uv run pytest tests/test_eval_harness.py -k "invariants or well_formed or expects_too_much"</tests>
<constraints>Keep the UNSAFE_APPROVAL and UNFAIR_DECLINE prefixes exactly. Check only the
fields a case sets. Every message says what was seen and what was expected.</constraints>
<done_when>Those tests pass and ruff is clean.</done_when>
```

## 3. Running, metrics, gates and reports (40 min)

```text
<task>Finish harness.py: EvalReport (metrics, by_tag, gate_results, passed,
markdown), run_eval, print_report, write_baseline</task>
<spec>lessons/06-evaluation/SPEC.md, the rest of the section, including the gate table</spec>
<tests>uv run pytest, then uv run underwriter eval</tests>
<constraints>Gate details read "actual ≤ limit". The baseline comparison applies only to a
full run of the same size. Never update evals/baseline.json unless asked.</constraints>
<done_when>The whole suite is green and eval prints PASSED: 32/32 cases with every gate passing.</done_when>
```

## 4. Prove it can fail (20 min)

Do one mutation drill from the guide yourself. It's the one sanctioned exception to
"don't touch `decision/policy.py`": change it, watch the eval fail, then revert before
you commit.
1. Change `dti_review_above` from 0.43 to 0.47 in `decision/policy.py`.
2. Run `uv run underwriter eval` and see the unsafe approvals.
3. Revert.

An eval that has never failed hasn't been tested.

## 5. Verify, review, learn (10 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest` and `uv run underwriter eval` are green.
- Your PR shows the failing eval output from step 4, and explains why cost and latency
  are release gates.

## Don't delegate

The gate limits in `evals/gates.json`, and the expected answer of any golden case you
add (`add-golden-case`). Both come from the business and the policy.
