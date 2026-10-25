---
name: clarify-before-building
description: Use before building anything non-trivial in this repo (a lesson module, a new rule, a new check, a change of behaviour) to find out what is actually wanted and record the answers in CLAUDE.md › Clarifications. Adapted from obra/superpowers brainstorming (MIT).
---

# Clarify before building

You build what you believe is wanted, and that belief is usually thinner than it
feels. In a lending system a wrong guess becomes a wrong decision, so find out first.
(Adapted from obra/superpowers `brainstorming`; see THIRD_PARTY_NOTICES.md.)

## 1. Look before you ask

Read these before your first message, and never ask what they already answer:

- CLAUDE.md, including **Clarifications** (settled questions stay settled)
- the lesson's `SPEC.md` and the tests it names
- `architecture/requirements.md`, the ADRs, `architecture/failure-modes.md`
- the policy text in `data/policies/` when a rule or threshold is involved

## 2. Decide whether anything is missing

- **Everything that matters is in the spec** (a SPEC.md module with its tests): say so
  in one line and go to `write-plan`.
- **Something that would change the code is open:** ask about it, one question per
  message, in plain words, saying what the answer changes. For example: "Does a bank
  outage stop the decision or only cost corroboration? Required means the case goes to
  a human; optional means it carries on with an info signal."

Typical open questions here:

- required or optional, for a new check;
- DECLINE or MANUAL_REVIEW, for a breach;
- `>` or `>=`, for a threshold, and the unit;
- what happens when an input is missing (never a default value);
- which policy section is the source.

## 3. Record the answer

Add one line under **Clarifications** in CLAUDE.md, in this shape:

```text
- **<the question, short>:** <the answer>. (<who or what settled it: policy §, ADR, lesson, instructor>)
```

## 4. Hand over

When nothing material is open, say what you understood in three lines or fewer, then
use `write-plan`.

<rules>
- One question per message. No lists of example answers hanging off it.
- Never pick an interpretation silently (karpathy-guidelines §1).
- Thresholds and expected outcomes come from the policy and the people who own it,
  never from you.
</rules>
