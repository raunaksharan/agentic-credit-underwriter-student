"""The LLM underwriting agent (lesson 3).

    case ─► build_context ─► prompt v1 ─► LLM ─► parse ─► validate ──ok──► proposal
                                              ▲                 │
                                              └── repair once ◄─┘ failed again ─► MANUAL_REVIEW

It implements the same UnderwritingAgent contract as lesson 1's rules stub, so the
workflow, the engine and every test around them are unchanged.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/03-structured-reasoning/SPEC.md; the tests are the answer key.
"""
