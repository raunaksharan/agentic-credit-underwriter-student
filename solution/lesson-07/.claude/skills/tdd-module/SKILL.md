---
name: tdd-module
description: Use when implementing a module, function or behaviour in this repo. Red, green, refactor against the lesson's given tests; write a new failing test first for any behaviour the given tests don't cover. Adapted from obra/superpowers test-driven-development (MIT).
---

# Test-driven, one module at a time

If you didn't watch the test fail, you don't know whether it tests the right thing.
(Adapted from obra/superpowers `test-driven-development`; see THIRD_PARTY_NOTICES.md.)

In a lesson, the failing tests already exist: they ship with the lesson and they are
the answer key. Outside a lesson, or for behaviour they don't cover, write the failing
test first.

## The loop

1. **Red.** Run the module's tests (`uv run pytest tests/test_<x>.py`, or `-k` for a
   subset). Read why they fail. An import error means the name isn't there yet; that's
   a valid red. A test that already passes is testing nothing new: say so.
2. **Green.** Write the smallest code that makes those tests pass, with the names and
   signatures from SPEC.md. No extra options, layers or features.
3. **Whole suite.** `uv run pytest`. "The other tests" means the project's tests,
   not just your file. Fix what you broke now.
4. **Refactor** only while green, and only your own code.
5. **Repeat** for the next function or module in the plan.

<rules>
- Never edit a file in `tests/` or `evals/` to make a test pass. If a test looks wrong,
  stop and say why, with the line.
- A new behaviour gets a new test, both sides of every threshold: just inside, exactly
  on, just outside, and the input missing.
- Exact arithmetic is code, never a model's estimate.
- If you wrote code before its test, delete it and start the loop again.
</rules>
