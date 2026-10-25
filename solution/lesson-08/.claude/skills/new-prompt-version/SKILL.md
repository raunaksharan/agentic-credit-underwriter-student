---
name: new-prompt-version
description: Create a new version of the underwriting prompt next to the current one and compare them on the eval before switching. Use when changing what the model is told, its examples, or its output instructions.
---

# A new prompt version

Prompts are versioned like code: the old one stays, the new one has its own version
string, and the eval decides.

1. **Say what should change and why,** and which failure it targets (an override, a
   repair, a citation miss). Name the golden cases that should improve.
2. **Copy, don't edit:** `agents/prompts/underwriting_v1.md` becomes
   `underwriting_v2.md` (or `underwriting_agent_v2.md` for the tool agent). Make the
   change there.
3. **Version string:** set `PROMPT_VERSION` to `underwriting-v2` (in
   `agents/underwriting.py` or `agents/tool_agent.py`), loading the new file. Every
   proposal and audit event then records which prompt produced it.
4. **Keep the contract:** the reply schema (`UnderwritingOutput`), the citation ids,
   the "you propose, the engine decides" instruction. No personal data goes in examples.
5. **Compare:** `uv run underwriter eval` before and after, from lesson 6 with
   `--markdown`. Report the deltas in pass rate, override rate, agent-valid rate and
   mean input tokens. A prompt that's longer and no better is a regression (the token
   gate).
6. **Live check (optional):** with your own key, `LLM_MODE=live` on `run-all`. The mock
   is deterministic and won't show wording effects.
7. **Decide and record:** keep v2 only if the eval says so. Add one line under
   Clarifications or Learnings in CLAUDE.md with the result.
