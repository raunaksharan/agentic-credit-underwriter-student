"""BM25 keyword retrieval, written out in full so students can read every term.

score(q, d) = Σ_t  idf(t) · tf(t,d)·(k1+1) / (tf(t,d) + k1·(1 − b + b·|d|/avgdl))

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/02-rag/SPEC.md; the tests are the answer key.
"""
