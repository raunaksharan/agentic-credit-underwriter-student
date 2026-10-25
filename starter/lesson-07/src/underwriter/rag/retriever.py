"""Hybrid policy retrieval: filter first, then keyword + vector search, fused with RRF.

    query ─► pre-filter (in force on as_of date, source types) ─► BM25 top-N ─┐
                                                                  vectors top-N┴► rrf_merge
         ─► abstain check ─► top-k chunks with citations

Pre-filtering, not post-filtering: a withdrawn circular is never a candidate, so it
can't crowd out the document that is actually in force.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from underwriter.rag.bm25 import BM25Index
from underwriter.rag.chunking import chunk_document
from underwriter.rag.embedding import Embedder, HashingEmbedder, cosine
from underwriter.rag.fusion import rrf_merge
from underwriter.rag.models import Chunk, DocumentMeta, RetrievalResult, RetrievedChunk
from underwriter.rag.parsers import parse_document

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
TODAY = date(2026, 10, 22)  # fixed so the course corpus behaves the same every year

# Abstain thresholds, set from the retrieval eval (lessons/02-rag/README.md): every
# answerable case scores above both, every must-abstain case below at least one.
MIN_BM25_COVERAGE = 0.14  # best BM25 score / best possible score for this query
MIN_COSINE = 0.17  # best cosine similarity


def load_manifest(data_dir: Path = DATA_DIR) -> list[DocumentMeta]:
    raw = json.loads((data_dir / "corpus" / "manifest.json").read_text())
    return [DocumentMeta.model_validate(d) for d in raw["documents"]]


def in_force(meta: DocumentMeta, docs: dict[str, DocumentMeta], on: date) -> bool:
    """Is this document the applicable version on date `on`?"""
    if meta.in_force_from and meta.in_force_from > on:
        return False
    if meta.withdrawn_on and meta.withdrawn_on <= on:
        return False
    successor = docs.get(meta.superseded_by or "")
    if successor and (successor.in_force_from or successor.effective_date) <= on:
        return False
    return True


class PolicyIndex:
    """All chunks of the corpus, with a BM25 index and a vector per chunk."""

    def __init__(self, docs: list[DocumentMeta], data_dir: Path = DATA_DIR,
                 embedder: Embedder | None = None) -> None:
        self.docs = {d.doc_id: d for d in docs}
        self.embedder = embedder or HashingEmbedder()
        self.chunks: list[Chunk] = []
        for meta in docs:
            self.chunks.extend(chunk_document(meta, parse_document(data_dir, meta)))
        texts = [f"{c.heading} {c.text}" for c in self.chunks]
        self.bm25 = BM25Index(texts)
        self.vectors = [self.embedder.embed(t) for t in texts]

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.chunks:
            out[c.doc_id] = out.get(c.doc_id, 0) + 1
        return out


@lru_cache(maxsize=1)
def default_index() -> PolicyIndex:
    return PolicyIndex(load_manifest())


class PolicyRetriever:
    def __init__(self, index: PolicyIndex | None = None, candidates: int = 50) -> None:
        self.index = index or default_index()
        self.candidates = candidates

    def _allowed(self, as_of: date, include_withdrawn: bool,
                 source_types: set[str] | None) -> set[int]:
        docs = self.index.docs
        ok_docs = {
            d.doc_id for d in docs.values()
            if (include_withdrawn or in_force(d, docs, as_of))
            and (source_types is None or d.source_type in source_types)
        }
        return {i for i, c in enumerate(self.index.chunks) if c.doc_id in ok_docs}

    def retrieve(self, query: str, k: int = 5, as_of: date | None = None,
                 include_withdrawn: bool = False,
                 source_types: set[str] | None = None) -> RetrievalResult:
        from underwriter.observability.tracing import set_attrs, span
        with span("retrieve", retrieval__k=k, retrieval__query_words=len(query.split()),
                  retrieval__include_withdrawn=include_withdrawn) as s:
            res = self._retrieve(query, k, as_of, include_withdrawn, source_types)
            set_attrs(s, retrieval__as_of=str(res.as_of), retrieval__abstained=res.abstained,
                      retrieval__results=len(res.results),
                      retrieval__top_ids=[r.chunk.chunk_id for r in res.results[:3]])
            return res

    def _retrieve(self, query: str, k: int, as_of: date | None, include_withdrawn: bool,
                  source_types: set[str] | None) -> RetrievalResult:
        as_of = as_of or TODAY
        allowed = self._allowed(as_of, include_withdrawn, source_types)

        bm25 = self.index.bm25.scores(query, allowed)
        bm25_ranked = sorted(bm25, key=lambda i: -bm25[i])[: self.candidates]

        qv = self.index.embedder.embed(query)
        cos = {i: cosine(qv, self.index.vectors[i]) for i in allowed}
        vec_ranked = sorted(cos, key=lambda i: -cos[i])[: self.candidates]

        fused = rrf_merge([[str(i) for i in bm25_ranked], [str(i) for i in vec_ranked]])
        bm25_pos = {i: r for r, i in enumerate(bm25_ranked, 1)}
        vec_pos = {i: r for r, i in enumerate(vec_ranked, 1)}
        results = [
            RetrievedChunk(chunk=self.index.chunks[int(i)], score=round(s, 5),
                           bm25=round(bm25.get(int(i), 0.0), 3), cosine=round(cos[int(i)], 3),
                           bm25_rank=bm25_pos.get(int(i)), vector_rank=vec_pos.get(int(i)))
            for i, s in fused[:k]
        ]

        coverage = (max(bm25.values()) / self.index.bm25.max_possible(query)) if bm25 else 0.0
        best_cos = max(cos.values(), default=0.0)
        if not results or coverage < MIN_BM25_COVERAGE or best_cos < MIN_COSINE:
            return RetrievalResult(
                query=query, as_of=as_of, results=[], abstained=True,
                reason=f"No applicable policy found (keyword coverage {coverage:.2f}, "
                       f"best similarity {best_cos:.2f})",
            )
        return RetrievalResult(query=query, as_of=as_of, results=results, abstained=False)
