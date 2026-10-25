"""Embeddings behind a port.

`HashingEmbedder` is the default: deterministic, offline, no API key, so tests and
classrooms behave identically. It hashes word tokens and character 4-grams into a
sparse vector, which captures spelling overlap ("verify" ~ "verification") but not
meaning ("denied" ~ "adverse action"). That gap is the point of lesson 2's
comparison: swap in a real embedding model (lesson 3's LLM port) and re-run the eval.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Protocol

from underwriter.rag.text import tokenize

Vector = dict[int, float]


class Embedder(Protocol):
    name: str

    def embed(self, text: str) -> Vector: ...


class HashingEmbedder:
    name = "hashing-v1"

    def __init__(self, dim: int = 2**18) -> None:
        self.dim = dim

    def _h(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dim

    def embed(self, text: str) -> Vector:
        feats: Counter[int] = Counter()
        for tok in tokenize(text, expand=True):
            feats[self._h("w:" + tok)] += 1.0
            padded = f"#{tok}#"
            for i in range(len(padded) - 3):
                feats[self._h("c:" + padded[i : i + 4])] += 0.5
        vec = {k: 1 + math.log(v) for k, v in feats.items()}  # sublinear tf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {k: v / norm for k, v in vec.items()}


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())
