---
name: add-retrieval-case
description: Add a retrieval eval case to evals/retrieval_cases.json (a question with the section it must cite, an as-of date case, or a must-abstain case). Use when retrieval misses something, a document is added, or a question should be answered with "no applicable policy".
---

# Add a retrieval eval case

The expected citation comes from reading the documents, never from what the retriever
returns today.

1. **Write the question** as an underwriter or the agent would ask it.
2. **Find the answer by reading** the policy or the regulation, and note the exact
   section and paragraph label.
3. **Add the case** to `cases` in `evals/retrieval_cases.json`, using the next free
   `R` id:

   ```json
   {"id": "R21", "query": "…", "expect": [{"doc_id": "reg-b-12cfr1002", "section": "1002.9", "label": "(a)"}]}
   ```

   - **Version questions:** add `"as_of": "YYYY-MM-DD"` and a `note` saying which
     version applies on that date.
   - **Out-of-scope questions** (weather, recipes, a product we don't offer):
     `{"id": "R22", "query": "…", "must_abstain": true}`.
   - Use `section_contains` when any paragraph of a section is acceptable.
4. **Run it:** `uv run underwriter eval-retrieval`. If the new case fails, decide
   whether retrieval or the case is wrong and say which. Never move `MIN_BM25_COVERAGE`
   or `MIN_COSINE` to make one case pass; that's a change for the whole suite, made with
   the instructor.
5. **Verify:** `/verify`.
