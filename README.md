# Enterprise Agentic AI Engineering: the course repo

FDE Academy · Instructor: Raunak Sharan

You build one system across the course: an agentic credit-underwriting platform for a
fictional lender, Meridian Digital Lending. Each lesson adds one layer. Everything runs
offline on a mock LLM, so you don't need an API key.

## Before every lab

```bash
git pull
```

Each lab adds one lesson to this repo. Then open `lessons/NN-*/START-HERE.md` for that
lesson and follow it from the top.

## What's in here

| Folder | What it is |
|---|---|
| `lessons/NN-*/` | The lesson guide (`README.md`), `START-HERE.md` (the commands), and the slides as a PDF |
| `solution/lesson-NN/` | The finished, working code for lesson NN. Run it first; copy from it if your own build gets stuck |
| `starter/lesson-NN/` | The starting point to build lesson NN yourself with Claude Code: that lesson's modules are empty, the tests are the answer key, and `lessons/NN-*/SPEC.md` and `PROMPTS.md` say what to build and how |

**Don't work inside this repo.** Copy a starter to your own folder (START-HERE shows
how), so `git pull` never clashes with your changes.

First time? Read [SETUP.md](SETUP.md).
