# Lesson 0 — Building with Claude Code: you steer, Claude types, the tests decide

> Most of this repo can be written by Claude. Your job is to decide what "right" means,
> make it checkable, and review what comes back.

**Slides:** [PDF](slides/lesson-00-building-with-claude.pdf)
**Duration:** 2 hours (50 min concepts, 70 min lab)
**Code at end of lesson:** labs start from `starter/lesson-NN`; finished code is in `solution/lesson-NN`

## Objectives

By the end of this lesson students can:

1. Run the loop: **plan → test → implement → verify → review**, with themselves steering.
2. Give Claude project context with a committed `CLAUDE.md` (context, scope, plan,
   clarifications, learnings from PRs) and keep it growing.
3. Use the repo's commands, process skills (adapted from Karpathy's guidelines and obra's
   Superpowers) and use-case skills, and the lint hook.
4. Build a lesson's modules from zero, from its SPEC.md, and finish with every check green.
5. Say which parts of a credit system they must not delegate, and why.

## Why this works on this repo

Generated code is only as good as the check it has to pass. This repo already has the
checks: typed contracts (lesson 1), unit tests on both sides of every threshold, a
retrieval eval (lesson 2), golden cases with safety invariants and release gates
(lesson 6). Claude writes the code; those checks decide whether it's right.

## What's in the repo

| File | What it does |
|---|---|
| `CLAUDE.md` | Context, scope, the plan rule, commands, the system rules (a seventh, on personal data, arrives in lesson 7), how to work, what not to touch, the code map, the skills and commands, **Clarifications** (settled questions) and **Learnings from PRs** |
| `.claude/settings.json` | Pre-approved safe commands (uv, pytest, ruff, underwriter, read-only git); `.env` reads denied; the lint hook |
| `.claude/hooks/lint.sh` | After every edit to a `.py` file, runs ruff on it; problems go straight back to Claude |
| `.claude/commands/` | Repeated actions, one command each: `/start-lesson`, `/clarify`, `/plan-lesson`, `/build-module`, `/verify`, `/review`, `/learn`, `/catch-up`, `/explain-decision`, `/trace`, `/eval-report` |
| `.claude/skills/` (process) | `karpathy-guidelines` (vendored), and adapted from Superpowers: `clarify-before-building`, `write-plan`, `tdd-module`, `debug-root-cause`, `verify-before-done`, `review-and-learn`. Sources and licences are in `THIRD_PARTY_NOTICES.md` |
| `.claude/skills/` (use case) | `add-policy-rule`, `add-tool-check`, `add-golden-case`, `add-sample-application`, `add-regulatory-document`, `add-retrieval-case`, `new-prompt-version`, `add-workflow-node`, `investigate-decision` |
| `lessons/NN-*/SPEC.md` | What to build in that lesson: the public API, behaviour and exact messages |
| `lessons/NN-*/PROMPTS.md` | How to build it, as XML-tagged prompts: clarify and plan, scaffold, one module per step, verify, review, learn |
| `workflows/` | Every repeatable procedure as its own file: start a lesson, build a module, catch up, and so on |

## The loop

| Step | You | Claude | Built-in feature |
|---|---|---|---|
| Clarify | Answer one question at a time | Asks what the spec leaves open, records answers | `/clarify`, Clarifications in CLAUDE.md |
| Plan | Read and correct the plan | Proposes files, tests, failure modes | Plan mode, `/plan-lesson` |
| Test | Confirm the tests prove the goal | Runs them red | Permissions allowlist |
| Implement | Watch, interrupt if it wanders | Writes code, fixes lint as it goes | Lint hook |
| Verify | Read the table | Runs every check | `/verify` |
| Review | Decide which findings are real | A fresh subagent reviews the diff | `/review` |
| Learn | Decide what's worth keeping | Writes one learning line | `/learn`, Learnings from PRs in CLAUDE.md |

This mirrors what Anthropic has published about its own use of Claude Code: plan
first, a team CLAUDE.md that records mistakes, TDD with check-ins, verification loops,
slash commands and hooks for routine work, and humans focused on review and steering.

## Agenda

| Time | Block |
|---|---|
| 0:00 | Why generated code needs checks, and why this repo already has them |
| 0:10 | CLAUDE.md: context, scope, plan, rules, clarifications, learnings from PRs |
| 0:20 | `.claude/`: permissions, the lint hook, commands, process and use-case skills |
| 0:35 | What not to delegate: thresholds, golden answers, your explanation |
| 0:45 | Where the skills come from: Karpathy's guidelines, Superpowers, skill-creator |
| 0:50 | Lab: Lesson 1 from `starter/lesson-01` |

## Setup

```bash
# install Claude Code first: https://code.claude.com/docs (pick your platform)
cd ~/fde-work/lesson-01        # your copy of starter/lesson-01 (START-HERE.md)
uv sync --all-groups
claude                                     # trust the folder when asked, so the settings load
```

Inside Claude Code: `/status` should list the project settings, and typing `/` should show
the repo's commands (`/start-lesson`, `/plan-lesson`, `/build-module`, `/verify`, …).

## Lab: Lesson 1 from the starter (70 min)

Follow `lessons/01-architecture/PROMPTS.md`, steps 1–4 (`workflows/start-a-lesson.md`
and `build-a-module-with-claude.md` explain the loop). Then do one round of each:

1. **Break the hook on purpose.** Ask Claude to add an unused import to any module.
   Watch the hook send ruff's complaint back, and Claude fix it.
2. **Catch a bad plan.** Ask for a plan that edits `tests/test_decision_engine.py` to
   make it pass. Point at CLAUDE.md and ask for a new plan.
3. **Record a learning.** When Claude gets something wrong, or `/review` finds something
   real, run `/learn <what happened>` and commit the new line under "Learnings from PRs".
4. **Settle a question.** When Claude asks something the spec leaves open, answer it
   and check that it landed under "Clarifications".

## What you must not delegate

| Don't delegate | Why |
|---|---|
| Policy thresholds (`decision/policy.py`) | Business commitments, signed off by people accountable for them |
| Golden-case expectations, eval sources | If the system writes the answer key, the eval proves nothing |
| The "why it works" paragraph in every PR | It's what the rubric grades, and what an interviewer will ask |
| Deciding which review findings are real | A reviewer that can't be overruled is a second author |

## Where the skills come from

The process skills are adapted from published agentic workflows and kept in the repo,
so every student gets the same behaviour without installing anything. Sources and
licences are in `.claude/skills/THIRD_PARTY_NOTICES.md`.

- **Karpathy-inspired guidelines** (forrestchang/andrej-karpathy-skills, MIT; a community
  project, not by Karpathy): think before coding, simplicity first, surgical changes,
  goal-driven execution. Vendored unchanged as `karpathy-guidelines`; CLAUDE.md's "How to
  work here" applies it to this repo.
- **Superpowers** (obra/superpowers, MIT): brainstorming, writing plans, TDD, systematic
  debugging, verification before completion, code review. Adapted as
  `clarify-before-building`, `write-plan`, `tdd-module`, `debug-root-cause`,
  `verify-before-done` and `review-and-learn`. Each one writes to this repo's places: the
  Clarifications and Learnings in CLAUDE.md, and plans in `docs/plans/`.
- **skill-creator** (Anthropic, `anthropics/skills`, Apache-2.0): drafts new skills. Not
  vendored; Lesson 9 uses it to turn your own repeated workflow into a skill.

To try the originals too, install them as plugins (`/plugin install
superpowers@claude-plugins-official`). Check each project's README first: plugins change
faster than course notes.

## Homework / deliverable

PR on top of your copy of `starter/lesson-01` containing:

- [ ] Lesson 1 calculations and engine, all tests green, `run-all` 8/8
- [ ] Your "why it works" paragraph (0% loans, gross vs net income, agent DECLINE → human)
- [ ] Any Clarifications you settled and Learnings from PRs you added to CLAUDE.md, or a
  note saying there were none
- [ ] The `/review` findings you rejected, and why

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Plan | Corrected before approval; names tests and failure modes | Approved as generated |
| Verification | Every check green, shown in the PR | "It works on my machine" |
| Review | Findings triaged, some rejected with reasons | All accepted, or none read |
| Explanation | In the student's words, specific | Pasted from Claude |
| CLAUDE.md | Grows with real clarifications and learnings | Untouched |

## Interview questions this lesson prepares for

- How do you use AI coding tools without shipping code you don't understand?
- What do you put in a CLAUDE.md (or equivalent), and how does it change over time?
- How do you stop an AI assistant from "fixing" a failing test by editing the test?
- Which parts of a regulated system would you never let an AI write unreviewed?

