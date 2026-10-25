# Third-party skills and the skills adapted from them

| Skill here | Source | Licence | How it's used |
|---|---|---|---|
| `karpathy-guidelines` | [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) (`skills/karpathy-guidelines`, checked 2026-10-25), from Andrej Karpathy's public notes on LLM coding pitfalls | MIT | Copied unchanged |
| `clarify-before-building` | [obra/superpowers](https://github.com/obra/superpowers) `brainstorming` (checked 2026-10-25) | MIT, © 2025 Jesse Vincent | Adapted: answers go to CLAUDE.md › Clarifications |
| `write-plan` | obra/superpowers `writing-plans` | MIT, © 2025 Jesse Vincent | Adapted: plans argue from the lesson's SPEC.md and failure modes |
| `tdd-module` | obra/superpowers `test-driven-development` | MIT, © 2025 Jesse Vincent | Adapted: the lesson's given tests are the first failing tests |
| `debug-root-cause` | obra/superpowers `systematic-debugging` | MIT, © 2025 Jesse Vincent | Adapted to this repo's traces and audit trail |
| `verify-before-done` | obra/superpowers `verification-before-completion` | MIT, © 2025 Jesse Vincent | Adapted: the gate is `/verify` |
| `review-and-learn` | obra/superpowers `requesting-code-review` and `receiving-code-review` | MIT, © 2025 Jesse Vincent | Adapted: each accepted finding becomes a line in CLAUDE.md › Learnings from PRs |

The use-case skills (`add-*`, `new-prompt-version`, `investigate-decision`) are this
course's own.

To use the originals as well, install them as plugins (check each project's README for
the current steps, since plugins change faster than course notes):

```text
/plugin install superpowers@claude-plugins-official
/plugin marketplace add anthropics/skills        # skill-creator lives here (Apache-2.0)
```

## MIT licence (obra/superpowers)

Copyright (c) 2025 Jesse Vincent

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be included in all copies
or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## MIT licence (forrestchang/andrej-karpathy-skills)

The project's README states the MIT licence; the same permission notice above applies,
with the copyright held by that project's authors.
