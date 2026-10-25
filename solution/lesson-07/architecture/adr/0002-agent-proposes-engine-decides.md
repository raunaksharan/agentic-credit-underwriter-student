# ADR-0002: The agent proposes; the engine decides

**Status:** Accepted · Lesson 1

## Context

The underwriting agent will be an LLM. It will usually be right and
occasionally confidently wrong. Policy is a regulatory commitment.

## Decision

The agent outputs an `AgentRecommendation` (a proposal). The deterministic
`DecisionEngine` produces the decision under one rule:

> **The agent may escalate. It may never relax policy.**

| Policy says | Agent says | Final | Overridden? |
|---|---|---|---|
| APPROVE | APPROVE | APPROVE | no |
| APPROVE | MANUAL_REVIEW | MANUAL_REVIEW | no (escalation allowed) |
| APPROVE | DECLINE | MANUAL_REVIEW | yes (no declines outside policy) |
| MANUAL_REVIEW | APPROVE | MANUAL_REVIEW | yes |
| DECLINE | APPROVE / MANUAL_REVIEW | DECLINE | yes |

Every override is recorded (`overridden_by_policy`) and becomes an evaluation
signal: a rising override rate means the agent and policy have drifted apart.

## Consequences

- Policy compliance does not depend on prompt quality.
- The agent's value is in explanation, evidence gathering and spotting what rules
  can't (escalation), not in having the last word.
- See APP-008: the lesson 1 stub approves a 43.9% DTI case; the engine routes it
  to review.
