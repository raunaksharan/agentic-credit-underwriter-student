# Setup (once, before Lesson 0)

You need four things: Python 3.13, uv, git and Claude Code.

1. **Python 3.13 and uv.** Install uv from https://docs.astral.sh/uv/. It can install
   Python for you: `uv python install 3.13`.
2. **git.** Check it with `git --version`.
3. **Claude Code.** Install it from https://code.claude.com/docs (pick your platform),
   then run `claude` once and sign in. Optional: students without Claude Code can do the
   labs by hand from the same SPEC.md files, and the instructor has a no-Claude mini
   track too.
4. **This repo:**

   ```bash
   git clone <the URL your instructor shares> fde-course
   cd fde-course
   ```

**Check it works.** Run the lesson's `START-HERE.md`, step 1, once Lesson 1 is released.
It ends with a line you can compare.

**Behind a corporate proxy?** If `uv sync` fails on certificates, set
`UV_SYSTEM_CERTS=1` and try again.
