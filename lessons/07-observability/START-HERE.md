# Lesson 7 · START HERE · Observability

Do the steps in order. Step 1 is for everyone, before the lesson is explained.

## 1. Run the finished code (everyone, 10 minutes)

From the course repo (run `git pull` first):

```bash
cd solution/lesson-07
uv sync --all-groups
uv run pytest                         # expect: 183 passed
uv run underwriter run-all            # expect: 8/8 match expected outcomes
uv run underwriter eval-retrieval     # expect: hit@5 1.00 · MRR 0.89 · abstain accuracy 1.00 · stale citations 0 · 20/20 cases pass
uv run underwriter eval               # expect: PASSED: 32/32 cases
```

Your last lines should match the `expect` comments. If they don't, put your hand up now: the rest of the lesson builds on this.

## 2. Build it yourself with Claude Code (the lab)

Copy the starter **out of the course repo**, so `git pull` never clashes with your work:

```bash
mkdir -p ~/fde-work
cp -r starter/lesson-07 ~/fde-work/lesson-07
cd ~/fde-work/lesson-07
git init -q && git add -A && git commit -qm start
uv sync --all-groups
uv run pytest --continue-on-collection-errors   # expect red: 30 passed, 9 errors
claude
```

(Windows PowerShell: `Copy-Item -Recurse starter\lesson-07 $HOME\fde-work\lesson-07`.)

You build these modules, from `lessons/07-observability/SPEC.md`:

- `src/underwriter/observability/metering.py`
- `src/underwriter/observability/tracing.py`
- `src/underwriter/llm/instrumented.py`
- `src/underwriter/observability/report.py`

Then follow `lessons/07-observability/PROMPTS.md` from the top. Inside Claude Code it starts with:

```text
/start-lesson 07
/plan-lesson 07
```

and ends with `/verify`, `/review` and `/learn`. You're done when your folder gives the same numbers as step 1.

**Stuck, or out of time?** Copy the module you're missing from `solution/lesson-07/` into your folder (or run `/catch-up 07`), then `/verify`.

## 3. Lab questions (if time permits)

They're in this lesson's guide, [README.md](README.md), under **Lab exercises**, with the homework after them.
