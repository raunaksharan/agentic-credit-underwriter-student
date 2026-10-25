"""Reciprocal rank fusion.

Lesson 2 exercise: students write this function from the docstring and the tests in
tests/test_rag_fusion.py. This is the reference solution.
"""

from __future__ import annotations


def rrf_merge(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Merge ranked lists of ids into one ranking.

    Each id scores Σ 1 / (k + rank) over the lists it appears in (rank starts at 1).
    Ranks, not raw scores, are combined, so BM25 scores and cosine similarities never
    need to be on the same scale. Ties are broken by first appearance, so the result
    is deterministic.

    >>> rrf_merge([["a", "b"], ["b", "c"]], k=0)
    [('b', 1.5), ('a', 1.0), ('c', 0.5)]
    """
    if k < 0:
        raise ValueError("k must be >= 0")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    order = 0
    for ranking in rankings:
        seen_here: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen_here:  # a duplicate within one list counts once
                continue
            seen_here.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
