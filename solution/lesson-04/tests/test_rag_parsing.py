"""Parsing and chunking the real corpus."""

import pytest

from underwriter.rag.chunking import MAX_WORDS
from underwriter.rag.parsers import parse_document
from underwriter.rag.retriever import DATA_DIR, default_index, load_manifest

DOCS = {d.doc_id: d for d in load_manifest()}


def labels(doc_id):
    return [p.label for s in parse_document(DATA_DIR, DOCS[doc_id]) for p in s.paragraphs]


def test_every_document_parses_to_text():
    for meta in DOCS.values():
        sections = parse_document(DATA_DIR, meta)
        assert sum(len(p.text.split()) for s in sections for p in s.paragraphs) > 300, meta.doc_id


def test_ecfr_labels_are_full_paths():
    # eCFR XML only carries one level per paragraph; the parser rebuilds the path
    assert "(c)(4)" in labels("reg-z-1026.43-current")
    assert "(a)(3)(vi)" in labels("reg-z-1026.43-current")
    assert "(b)(2)" in labels("reg-b-12cfr1002")


def test_versioning_trap_is_in_the_text():
    old = parse_document(DATA_DIR, DOCS["reg-z-1026.43-2020"])
    new = parse_document(DATA_DIR, DOCS["reg-z-1026.43-current"])
    find = lambda secs: [p.text for s in secs for p in s.paragraphs if p.label == "(e)(2)(vi)"]  # noqa: E731
    assert "43 percent" in find(old)[0]
    assert "43 percent" not in find(new)[0]


def test_federal_register_pdf_is_cut_to_its_own_document():
    text = " ".join(p.text for s in parse_document(DATA_DIR, DOCS["cfpb-circular-2022-03"])
                    for p in s.paragraphs)
    assert "complex algorithms" in text
    assert "11 CFR 109.10" not in text  # the FEC rule sharing the first page


def test_sr_letter_skips_repeated_attachment_pages():
    text = " ".join(p.text for s in parse_document(DATA_DIR, DOCS["frb-sr-26-2"])
                    for p in s.paragraphs)
    assert "supersedes" in text and "MODEL DEVELOPMENT" not in text


def test_chunks_respect_size_and_section_limits():
    idx = default_index()
    assert len({c.chunk_id for c in idx.chunks}) == len(idx.chunks)
    assert max(len(c.text.split()) for c in idx.chunks) <= MAX_WORDS * 1.5
    assert all(c.citation for c in idx.chunks)


@pytest.mark.parametrize("doc_id", sorted(DOCS))
def test_every_document_has_chunks(doc_id):
    assert default_index().stats().get(doc_id, 0) > 0
