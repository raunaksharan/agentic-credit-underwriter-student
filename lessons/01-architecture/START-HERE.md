# Lesson 1 · START HERE · Business problem to AI architecture

Do the steps in order. Step 1 is for everyone, before the lesson is explained.

## 1. Run the finished code (everyone, 10 minutes)

From the course repo (run `git pull` first):

```bash
cd solution/lesson-01
uv sync --all-groups
uv run pytest                         # expect: 50 passed
uv run underwriter run-all            # expect: 8/8 match expected outcomes
```

Your last lines should match the `expect` comments. If they don't, put your hand up now: the rest of the lesson builds on this.

## 2. Build it yourself with Claude Code (the lab)

Copy the starter **out of the course repo**, so `git pull` never clashes with your work:

```bash
mkdir -p ~/fde-work
cp -r starter/lesson-01 ~/fde-work/lesson-01
cd ~/fde-work/lesson-01
git init -q && git add -A && git commit -qm start
uv sync --all-groups
uv run pytest --continue-on-collection-errors   # expect red: 10 passed, 3 errors
claude
```

(Windows PowerShell: `Copy-Item -Recurse starter\lesson-01 $HOME\fde-work\lesson-01`.)

You build these modules, from `lessons/01-architecture/SPEC.md`:

- `src/underwriter/risk/calculations.py`
- `src/underwriter/decision/engine.py`

Then follow `lessons/01-architecture/PROMPTS.md` from the top. Inside Claude Code it starts with:

```text
/start-lesson 01
/plan-lesson 01
```

and ends with `/verify`, `/review` and `/learn`. You're done when your folder gives the same numbers as step 1.

**Stuck, or out of time?** Copy the module you're missing from `solution/lesson-01/` into your folder (or run `/catch-up 01`), then `/verify`.

## 3. Lab questions (if time permits)

They're in this lesson's guide, [README.md](README.md), under **Lab exercises**, with the homework after them.
