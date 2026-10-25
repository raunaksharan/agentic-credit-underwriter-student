"""Deterministic decision engine.

The engine does two things:
1. Evaluates the policy against the case's verified facts (metrics + signals).
2. Reconciles that with the agent's proposal under one rule:
   **the agent may escalate, it may never relax policy.**

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/01-architecture/SPEC.md; the tests are the answer key.
"""
