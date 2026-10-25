"""The underwriting workflow as a LangGraph graph (lesson 5).

    START → intake → income → checks → analyze → policy → agent → engine ─┬─→ END
               │        │        │         │                               │
               └────────┴────────┴─────────┴──→ escalate ──→ human_review ←┘ (MANUAL_REVIEW)
                                                                   │
                                                          interrupt() │ resume(HumanReview)
                                                                   ▼
                                                                  END

- **Typed state.** `UnderwritingState` is the only thing nodes share. Each node reads
  what it needs and returns the keys it changed; `audit` is appended, never replaced.
- **Per-node policy.** Every node runs through `run_node` with its own timeout, retry
  count and failure mode (`NODE_POLICIES`). Required steps escalate; policy retrieval
  degrades; the agent has its own fallback.
- **Human-review edge.** MANUAL_REVIEW goes to `human_review`, which queues the case
  and, when the run is interactive, pauses the graph with `interrupt()` until a
  reviewer resumes it with a `HumanReview`. The pause is checkpointed by thread id.

The nodes call the same components as lessons 1–4; only the control flow moved here.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/05-agentic-workflows/SPEC.md; the tests are the answer key.
"""
