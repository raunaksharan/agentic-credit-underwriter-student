"""Split sections into retrievable chunks.

Rules (each is a teaching decision, see lessons/02-rag/README.md):

1. Never cross a section boundary: a chunk cites exactly one section.
2. Prefer to break at a top-level paragraph, so "(b)(2)" stays with its sub-paragraphs.
3. Cap chunk size (MAX_WORDS) so one chunk doesn't swamp the context window.
4. Very long paragraphs are split on sentence boundaries.
"""

from __future__ import annotations

import re

from underwriter.rag.models import Chunk, DocumentMeta, Paragraph, Section

MAX_WORDS = 220
MIN_WORDS = 60

_SENT = re.compile(r"(?<=[.;:])\s+(?=[A-Z(])")


def _citation(meta: DocumentMeta, section: Section, label: str) -> str:
    sid = section.section_id
    if meta.source_type == "internal_policy":
        return f"MDL policy §{sid} {section.heading}"
    if sid.startswith("Supplement I to Part 1002"):
        rest = sid.removeprefix("Supplement I to Part 1002").strip() or section.heading
        return f"12 CFR 1002 Supp. I, {rest}"
    if sid.startswith("Appendix") and meta.doc_id.startswith("reg-b"):
        return f"12 CFR 1002, {sid.replace(' to Part 1002', '')}"
    if sid.startswith("Appendix-") and meta.doc_id.startswith("ftc-"):
        return f"16 CFR 681, Appendix {sid.split('-')[1]}{label}"
    if meta.format in ("xml", "html") and re.match(r"^\d+\.\d+$", sid):
        part = {"reg-b": "12 CFR", "reg-z": "12 CFR", "ftc-": "16 CFR", "cip-": "31 CFR"}
        prefix = next((v for k, v in part.items() if meta.doc_id.startswith(k)), "CFR")
        return f"{prefix} {sid}{label}"
    return f"{meta.title.split(':')[0]}, {sid}"


def _top(label: str) -> str:
    """Top-level part of a label: "(b)(2)" -> "(b)", "4.2" -> "4"."""
    if label.startswith("("):
        return label[: label.find(")") + 1]
    return label.split(".")[0]


def _split_long(p: Paragraph) -> list[Paragraph]:
    words = p.text.split()
    if len(words) <= MAX_WORDS:
        return [p]
    out, buf = [], []
    for sent in _SENT.split(p.text):
        if buf and len(" ".join(buf + [sent]).split()) > MAX_WORDS:
            out.append(Paragraph(label=p.label, text=" ".join(buf)))
            buf = []
        buf.append(sent)
    if buf:
        out.append(Paragraph(label=p.label, text=" ".join(buf)))
    return out


def chunk_section(meta: DocumentMeta, section: Section,
                  used: dict[str, int] | None = None) -> list[Chunk]:
    paras = [q for p in section.paragraphs for q in _split_long(p)]
    groups: list[list[Paragraph]] = []
    current: list[Paragraph] = []
    for p in paras:
        size = sum(len(q.text.split()) for q in current)
        new_top = current and _top(p.label) != _top(current[-1].label)
        if current and (size + len(p.text.split()) > MAX_WORDS or (new_top and size >= MIN_WORDS)):
            groups.append(current)
            current = []
        current.append(p)
    if current:
        groups.append(current)

    chunks = []
    used = {} if used is None else used  # shared across a document so ids stay unique
    for g in groups:
        first = g[0].label
        text = " ".join(f"{p.label} {p.text}".strip() for p in g)
        # stable, readable ids: "reg-b-12cfr1002#1002.9(b)(2)", "mdl-upl-policy-3.2#4";
        # a suffix only when one paragraph was split into several chunks
        base = f"{meta.doc_id}#{section.section_id}{first if first.startswith('(') else ''}"
        n = used.get(base, 0)
        used[base] = n + 1
        chunks.append(Chunk(
            chunk_id=base if n == 0 else f"{base}~{n}",
            doc_id=meta.doc_id, section_id=section.section_id, heading=section.heading,
            first_label=first, text=text, title=meta.title, source_type=meta.source_type,
            status=meta.status, citation=_citation(meta, section, first),
        ))
    return chunks


def chunk_document(meta: DocumentMeta, sections: list[Section]) -> list[Chunk]:
    used: dict[str, int] = {}
    return [c for s in sections for c in chunk_section(meta, s, used)]
