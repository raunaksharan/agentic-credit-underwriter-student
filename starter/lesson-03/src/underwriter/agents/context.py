"""Context engineering: decide exactly what the model sees.

Three rules:

1. **Minimise.** The model never sees the applicant's name, date of birth, ID
   digits, email or address. It doesn't need them to judge affordability, and what it
   never sees it can never leak or be biased by.
2. **Give everything an id.** Every fact, signal, document and policy excerpt carries
   an id the model must cite. That makes citations checkable (validators.py).
3. **Prioritise within a budget.** Signals first, then metrics, then policy excerpts,
   then the application summary. Policy excerpts are trimmed and, if needed, dropped,
   lowest priority first, so the prompt stays under MAX_CONTEXT_CHARS.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/03-structured-reasoning/SPEC.md; the tests are the answer key.
"""
