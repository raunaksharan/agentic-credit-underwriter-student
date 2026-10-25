"""Tools the underwriting agent may call (lesson 4).

The allow-list is the security boundary. The agent can look things up and ask for
documents; it cannot approve, decline, change data or call anything not listed here.
Each tool validates its arguments and returns a small JSON result with citable ids.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/04-tool-agents/SPEC.md; the tests are the answer key.
"""
