"""BM25 keyword retrieval, written out in full so students can read every term.

score(q, d) = Σ_t  idf(t) · tf(t,d)·(k1+1) / (tf(t,d) + k1·(1 − b + b·|d|/avgdl))
"""

from __future__ import annotations

import math
from collections import Counter

from underwriter.rag.text import tokenize


class BM25Index:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokenize(d)) for d in docs]
        self.lengths = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = sum(self.lengths) / max(len(self.lengths), 1)
        df: Counter[str] = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.unseen_idf = math.log(1 + (n + 0.5) / 0.5)  # a term no chunk contains

    def scores(self, query: str, allowed: set[int] | None = None) -> dict[int, float]:
        q = set(tokenize(query, expand=True))
        out: dict[int, float] = {}
        for i, tf in enumerate(self.tfs):
            if allowed is not None and i not in allowed:
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    norm = f + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avgdl)
                    s += self.idf[t] * f * (self.k1 + 1) / norm
            if s > 0:
                out[i] = s
        return out

    def max_possible(self, query: str) -> float:
        """Upper bound used to normalise scores for the abstain decision.

        Query terms the corpus has never seen count at full weight: a question about
        "pasta recipes" should look poorly covered, not well covered by "fresh".
        """
        q = set(tokenize(query, expand=True))
        return sum(self.idf.get(t, self.unseen_idf) * (self.k1 + 1) for t in q) or 1.0
