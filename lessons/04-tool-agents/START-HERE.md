# Lesson 4 · START HERE · Tool-using agents

Do the steps in order. Step 1 is for everyone, before the lesson is explained.

## 1. Run the finished code (everyone, 10 minutes)

From the course repo (run `git pull` first):

```bash
cd solution/lesson-04
uv sync --all-groups
uv run pytest                         # expect: 130 passed
uv run underwriter run-all            # expect: 8/8 match expected outcomes
uv run underwriter eval-retrieval     # expect: hit@5 1.00 · MRR 0.89 · abstain accuracy 1.00 · stale citations 0 · 20/20 cases pass
```

Your last lines should match the `expect` comments. If they don't, put your hand up now: the rest of the lesson builds on this.

## 2. Build it yourself with Claude Code (the lab)

Copy the starter **out of the course repo**, so `git pull` never clashes with your work:

```bash
mkdir -p ~/fde-work
cp -r starter/lesson-04 ~/fde-work/lesson-04
cd ~/fde-work/lesson-04
git init -q && git add -A && git commit -qm start
uv sync --all-groups
uv run pytest --continue-on-collection-errors   # expect red: 54 passed, 4 errors
claude
```

(Windows PowerShell: `Copy-Item -Recurse starter\lesson-04 $HOME\fde-work\lesson-04`.)

You build these modules, from `lessons/04-tool-agents/SPEC.md`:

- `src/underwriter/tools/checks.py`
- `src/underwriter/agents/tools.py`
- `src/underwriter/agents/tool_agent.py`

Then follow `lessons/04-tool-agents/PROMPTS.md` from the top. Inside Claude Code it starts with:

```text
/start-lesson 04
/plan-lesson 04
```

and ends with `/verify`, `/review` and `/learn`. You're done when your folder gives the same numbers as step 1.

**Stuck, or out of time?** Copy the module you're missing from `solution/lesson-04/` into your folder (or run `/catch-up 04`), then `/verify`.

## 3. Lab questions (if time permits)

They're in this lesson's guide, [README.md](README.md), under **Lab exercises**, with the homework after them.
