---
name: verify-before-done
description: Use before saying anything is done, fixed or passing, and before every commit or PR in this repo. Runs the checks fresh and reports their actual output. Adapted from obra/superpowers verification-before-completion (MIT).
---

# Evidence before claims

No completion claim without fresh verification evidence. (Adapted from obra/superpowers
`verification-before-completion`; see THIRD_PARTY_NOTICES.md.)

## The gate

1. **Identify** the command that proves the claim. In this repo it is `/verify`: ruff,
   pytest, `run-all` (8/8), and from lesson 2 `eval-retrieval`, from lesson 6 `eval`.
2. **Run** it in full, now, not from memory of an earlier run.
3. **Read** the output: the exit status, the counts, the first failing line.
4. **Then** say what passed and what didn't, with the numbers ("182 passed; run-all
   8/8; eval 32/32").

<rules>
- "Should work", "looks right" and "I fixed it" are not results.
- A check you skipped is reported as skipped, with the reason.
- A red check is reported as red even when you think it's unrelated; say why you think
  so.
</rules>
