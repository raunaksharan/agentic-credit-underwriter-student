"""Split sections into retrievable chunks.

Rules (each is a teaching decision, see lessons/02-rag/README.md):

1. Never cross a section boundary: a chunk cites exactly one section.
2. Prefer to break at a top-level paragraph, so "(b)(2)" stays with its sub-paragraphs.
3. Cap chunk size (MAX_WORDS) so one chunk doesn't swamp the context window.
4. Very long paragraphs are split on sentence boundaries.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/02-rag/SPEC.md; the tests are the answer key.
"""
