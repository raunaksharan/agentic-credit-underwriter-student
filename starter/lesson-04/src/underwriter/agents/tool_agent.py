"""A bounded tool-calling underwriting agent (lesson 4).

    case ─► context ─► LLM ─┬─ call_tool ─► allow-list ─► tool ─► result ─┐
                            │      ▲                                        │
                            │      └────────────────────────────────────────┘
                            └─ final ─► validate (repair once) ─► proposal

Four limits make the loop safe to run unattended:

1. **Allow-list.** Only the tools in agents/tools.py exist. Anything else is refused
   and the refusal goes back to the model as a tool result, not an exception.
2. **Step cap.** At most MAX_TOOL_CALLS tool calls, then the agent must answer.
3. **Deadline.** A wall-clock budget for the whole loop.
4. **Fallback.** Hitting a limit, or failing validation twice, gives MANUAL_REVIEW with
   a machine-readable reason (AGENT_LIMIT_REACHED, INVALID_MODEL_OUTPUT,
   MODEL_UNAVAILABLE). The engine still decides.

The agent only proposes. Its tools read and request; none of them decides.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/04-tool-agents/SPEC.md; the tests are the answer key.
"""
