"""Hybrid policy retrieval: filter first, then keyword + vector search, fused with RRF.

    query ─► pre-filter (in force on as_of date, source types) ─► BM25 top-N ─┐
                                                                  vectors top-N┴► rrf_merge
         ─► abstain check ─► top-k chunks with citations

Pre-filtering, not post-filtering: a withdrawn circular is never a candidate, so it
can't crowd out the document that is actually in force.

You build this module in this lesson. Its public API, behaviour and exact messages
are in lessons/02-rag/SPEC.md; the tests are the answer key.
"""
