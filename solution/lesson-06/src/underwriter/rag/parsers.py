"""Turn each source format into a list of Sections.

Real documents arrive in different shapes, and each loses structure differently:

    eCFR XML   rich structure: sections (DIV8), appendices (DIV9), labelled paragraphs
    eCFR HTML  same content, structure in CSS classes and data attributes
    PDF        structure mostly lost: we recover headings with patterns, and must
               cut the document out of a Federal Register page it shares with others
    Markdown   our internal policy: numbered sections and clauses
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

from underwriter.rag.models import DocumentMeta, Paragraph, Section

logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noise here

_WS = re.compile(r"\s+")
# "(a)", "(b)(2)", "(c)(4)(i)" at the start of a regulatory paragraph
_LABEL = re.compile(r"^\s*((?:\([0-9a-zA-Z]{1,5}\))+)\s*")


def _clean(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _split_label(text: str) -> tuple[str, str]:
    m = _LABEL.match(text)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


_ROMAN = re.compile(r"^(?=[ivxl]+$)l?x{0,3}(ix|iv|v?i{0,3})$")
_EMBEDDED = re.compile(r"[—-]\s*((?:\([0-9a-zA-Z]{1,5}\))+)\s")


class _LabelPath:
    """Rebuild full paragraph references from eCFR's per-level labels.

    eCFR XML gives each paragraph only its own level's label: "(c)", then "(4)", then
    "(i)". Citations need the full path "(c)(4)(i)". CFR levels run: a → 1 → i → A,
    then italic 1 and i. A paragraph can also open a deeper level inline, as in
    "(a) Notification—(1) When notification is required."
    """

    def __init__(self) -> None:
        self.stack: list[tuple[int, str]] = []

    @staticmethod
    def _roman(tok: str) -> int:
        vals = {"i": 1, "v": 5, "x": 10, "l": 50}
        total = 0
        for a, b in zip(tok, tok[1:] + " ", strict=True):
            total += -vals[a] if vals.get(b, 0) > vals[a] else vals[a]
        return total

    def _at(self, level: int) -> str | None:
        return next((t for lv, t in reversed(self.stack) if lv == level), None)

    def _follows(self, level: int, tok: str) -> bool:
        """True if tok is the next sibling of the label currently open at `level`."""
        prev = self._at(level)
        if prev is None:
            return False
        if level in (1, 4):
            return tok.isdigit() and int(tok) == int(prev) + 1
        if level in (2, 5):
            return bool(_ROMAN.match(tok)) and self._roman(tok) == self._roman(prev) + 1
        return len(tok) == 1 and len(prev) == 1 and ord(tok) == ord(prev) + 1

    def _level(self, tok: str) -> int:
        current = self.stack[-1][0] if self.stack else -1
        if tok.isupper():
            return 3
        if tok.isdigit():
            if tok == "1":
                return 4 if current == 3 else 1
            if self._follows(4, tok):
                return 4
            return 1
        if _ROMAN.match(tok):
            if len(tok) == 1 and self._follows(0, tok):
                return 0  # (h) then (i): a letter, not a numeral
            if tok == "i":
                return 5 if current == 4 else 2 if self.stack else 0
            if self._follows(5, tok):
                return 5
            if self._follows(2, tok):
                return 2
            return 2
        return 0

    def push(self, label: str) -> str:
        for tok in re.findall(r"\(([0-9a-zA-Z]+)\)", label):
            level = self._level(tok)
            while self.stack and self.stack[-1][0] >= level:
                self.stack.pop()
            self.stack.append((level, tok))
        return self.current

    @property
    def current(self) -> str:
        return "".join(f"({t})" for _, t in self.stack)


# ---------------------------------------------------------------------------
# eCFR XML
# ---------------------------------------------------------------------------


def parse_ecfr_xml(path: Path, meta: DocumentMeta) -> list[Section]:
    root = ET.parse(path).getroot()
    sections: list[Section] = []

    for div in root.iter("DIV8"):  # regulation sections, e.g. 1002.9
        paras = []
        path = _LabelPath()
        for p in div.iter("P"):
            label, body = _split_label(_clean("".join(p.itertext())))
            if label:
                path.push(label)
                head = body[:200]
                for m in _EMBEDDED.finditer(head):  # "(a) Notification—(1) When ..."
                    path.push(m.group(1))
            label = path.current  # continuation paragraphs inherit the current path
            if body:
                paras.append(Paragraph(label=label, text=body))
        sections.append(Section(doc_id=meta.doc_id, section_id=div.get("N", ""),
                                heading=_clean(div.findtext("HEAD") or ""), paragraphs=paras))

    for div in root.iter("DIV9"):  # appendices and the official interpretations
        name = div.get("N", "")
        current = Section(doc_id=meta.doc_id, section_id=name,
                          heading=_clean(div.findtext("HEAD") or name), paragraphs=[])
        for el in div:
            tag, text = el.tag, _clean("".join(el.itertext()))
            if not text:
                continue
            if tag in ("HD1", "HD2", "HD3"):
                # Supplement I is organised by headings such as "9(b)(2) Statement of
                # specific reasons." Start a new section at each one so citations are precise.
                if current.paragraphs:
                    sections.append(current)
                sub = text.split(" ")[0] if tag == "HD3" else text
                current = Section(doc_id=meta.doc_id, section_id=f"{name} {sub}".strip(),
                                  heading=text, paragraphs=[])
            elif tag in ("P", "FP", "FP-1", "FP-DASH"):
                current.paragraphs.append(Paragraph(text=text))
        if current.paragraphs:
            sections.append(current)
    return sections


# ---------------------------------------------------------------------------
# eCFR HTML (renderer API)
# ---------------------------------------------------------------------------


def parse_ecfr_html(path: Path, meta: DocumentMeta) -> list[Section]:
    soup = BeautifulSoup(path.read_text(), "html.parser")
    sections: list[Section] = []
    for div in soup.select("div.section, div.appendix"):
        head = div.find(["h4", "h3", "h2"])
        heading = _clean(head.get_text(" ")) if head else ""
        section_id = div.get("id") or heading
        paras = []
        for p in div.find_all("p"):
            title = p.get("data-title", "")
            for span in p.select("span.paragraph-hierarchy"):
                span.decompose()  # the "( a )" marker; the full label is in data-title
            text = _clean(p.get_text(" "))
            title = re.sub(r"</?em>", "", title)
            label = title[title.index("("):] if title and "(" in title else ""
            if text:
                paras.append(Paragraph(label=label, text=text))
        sections.append(Section(doc_id=meta.doc_id, section_id=section_id, heading=heading,
                                paragraphs=paras))
    return sections


# ---------------------------------------------------------------------------
# PDF (Federal Register and Federal Reserve)
# ---------------------------------------------------------------------------

_PDF_HEADING = re.compile(
    r"^(SUMMARY:|SUPPLEMENTARY INFORMATION:|Question Presented|Response|Analysis|Background|"
    r"[IVX]+\.\s+[A-Z][A-Za-z ,/&-]+|[A-Z][a-z]+(?: [A-Za-z]+){0,5})\s*$"
)
_KNOWN_SUBHEADINGS = {"Model Development", "Model Use", "Model Validation", "Ongoing Monitoring",
                      "Outcomes Analysis", "Model Inventory", "Third-Party Models"}


def _extract_pdf_text(path: Path, meta: DocumentMeta) -> str:
    reader = PdfReader(path)
    pages = reader.pages
    if meta.pages:
        pages = [reader.pages[i - 1] for i in meta.pages]
    text = "\n".join(p.extract_text() or "" for p in pages)
    if meta.fr_doc:
        # A Federal Register page holds several agencies' documents. Ours ends at its own
        # "[FR Doc. <number>" line and starts after the previous document's BILLING CODE.
        number = meta.fr_doc.replace("-", "[–-]")
        end = re.search(rf"\[FR Doc\. {number}", text)
        if not end:
            raise ValueError(f"{meta.doc_id}: FR Doc {meta.fr_doc} not found")
        starts = [m.end() for m in re.finditer(r"BILLING CODE [^\n]*\n", text[: end.start()])]
        text = text[(starts[-1] if starts else 0): end.start()]
    # undo line-wrap hyphenation ("rule- making") and Federal Register running headers
    text = re.sub(r"(\w)[–-]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"^.*Federal Register / Vol\..*$", "", text, flags=re.M)
    return text


def parse_pdf(path: Path, meta: DocumentMeta) -> list[Section]:
    text = _extract_pdf_text(path, meta)
    sections: list[Section] = []
    current = Section(doc_id=meta.doc_id, section_id="Preamble", heading="Preamble", paragraphs=[])
    buf: list[str] = []

    def flush_paragraph() -> None:
        if buf:
            current.paragraphs.append(Paragraph(text=_clean(" ".join(buf))))
            buf.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.isdigit():
            flush_paragraph()
            continue
        is_heading = bool(_PDF_HEADING.match(line)) and (
            line.endswith(":") or line.isupper() or re.match(r"^[IVX]+\.", line)
            or line in ("Question Presented", "Response", "Analysis", "Background")
            or line in _KNOWN_SUBHEADINGS
        )
        if is_heading:
            flush_paragraph()
            if current.paragraphs:
                sections.append(current)
            name = line.rstrip(":").strip()
            current = Section(doc_id=meta.doc_id, section_id=name, heading=name, paragraphs=[])
            continue
        buf.append(line)
        if line.endswith((".", ":", ";")) and len(" ".join(buf).split()) > 60:
            flush_paragraph()
    flush_paragraph()
    if current.paragraphs:
        sections.append(current)
    return sections


# ---------------------------------------------------------------------------
# Internal policy (Markdown)
# ---------------------------------------------------------------------------


def parse_policy_markdown(path: Path, meta: DocumentMeta) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    for line in path.read_text().splitlines():
        h = re.match(r"^## (\d+)\. (.+)$", line)
        if h:
            current = Section(doc_id=meta.doc_id, section_id=h.group(1), heading=h.group(2),
                              paragraphs=[])
            sections.append(current)
            continue
        clause = re.match(r"^(\d+\.\d+) (.+)$", line)
        if current and clause:
            current.paragraphs.append(Paragraph(label=clause.group(1), text=clause.group(2)))
        elif current and line.strip() and current.paragraphs and not line.startswith("#"):
            current.paragraphs[-1].text += " " + line.strip()  # wrapped clause line
    for s in sections:
        for p in s.paragraphs:
            p.text = _clean(p.text.replace("**", ""))
    return sections


PARSERS = {"xml": parse_ecfr_xml, "html": parse_ecfr_html, "pdf": parse_pdf,
           "md": parse_policy_markdown}


def parse_document(data_dir: Path, meta: DocumentMeta) -> list[Section]:
    return PARSERS[meta.format](data_dir / meta.path, meta)
