"""Typed contracts for retrieval (lesson 2)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class DocumentMeta(BaseModel):
    """One entry of data/corpus/manifest.json."""

    doc_id: str
    title: str
    issuer: str
    source_type: str = Field(description="internal_policy | regulation | guidance | notice")
    format: str
    path: str
    url: str | None = None
    effective_date: date
    status: str = Field(description="current | superseded | withdrawn")
    in_force_from: date | None = None
    withdrawn_on: date | None = None
    superseded_by: str | None = None
    supersedes: str | None = None
    fr_doc: str | None = None
    pages: list[int] | None = None


class Paragraph(BaseModel):
    label: str = Field(default="", description="e.g. '(b)(2)' or '9(b)(2)-1'; empty if none")
    text: str


class Section(BaseModel):
    doc_id: str
    section_id: str = Field(description="e.g. '1002.9', 'Supplement I 9(b)(2)', '4', 'Analysis'")
    heading: str
    paragraphs: list[Paragraph]


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    section_id: str
    heading: str
    first_label: str
    text: str
    # denormalised document metadata, so filters and citations need no join
    title: str
    source_type: str
    status: str
    citation: str = Field(description="human-readable reference, e.g. '12 CFR 1002.9(b)(2)'")


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float = Field(description="fused RRF score")
    bm25: float
    cosine: float
    bm25_rank: int | None
    vector_rank: int | None


class RetrievalResult(BaseModel):
    query: str
    as_of: date
    results: list[RetrievedChunk]
    abstained: bool
    reason: str = ""

    @property
    def citations(self) -> list[str]:
        return [r.chunk.chunk_id for r in self.results]
