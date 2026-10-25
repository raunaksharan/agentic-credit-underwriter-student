# Lesson 2 spec: hybrid retrieval with citations and abstain

**You build:** four modules in `src/underwriter/rag/`:
- `fusion.py`
- `bm25.py`
- `chunking.py`
- `retriever.py`

**Given (the seed):** the Lesson 1 reference code, plus:
- `rag/parsers.py` (eCFR XML, HTML, Federal Register PDFs, Markdown into sections and
  labelled paragraphs), `rag/text.py` (`tokenize`, with query expansion) and
  `rag/models.py` (`DocumentMeta`, `Section`, `Paragraph`, `Chunk`, `RetrievedChunk`,
  `RetrievalResult`);
- `rag/embedding.py` (`HashingEmbedder`, `cosine`) and `rag/analyzer.py` (the policy
  analyzer the workflow calls);
- `evaluation/retrieval.py`, `evals/retrieval_cases.json` (20 cases) and the corpus with
  its checksums.

**Answer key:**
- tests: `tests/test_rag_fusion.py`, `tests/test_rag_parsing.py` (chunking) and
  `tests/test_rag_retriever.py`;
- the eval: `uv run underwriter eval-retrieval` must pass all 20 cases, with hit@5 at
  least 0.94, abstain accuracy 1.0 and 0 stale citations.

**At the start:** `tests/test_rag_parsing.py` and `tests/test_rag_retriever.py` build the
index when they're imported, so they error at collection until chunking and the index
work. Use `--continue-on-collection-errors`, or
one file at a time.

```bash
uv run pytest tests/test_rag_fusion.py
uv run pytest tests/test_rag_parsing.py
uv run underwriter ingest            # 664 chunks from 11 documents when chunking is right
uv run pytest tests/test_rag_retriever.py && uv run underwriter eval-retrieval
```

## `fusion.py`: reciprocal rank fusion

`rrf_merge(rankings, k=60)` merges ranked lists of ids:

- Each id scores `Σ 1/(k + rank)` over the lists it appears in, with rank starting at 1.
- An id repeated within one list counts once.
- The result is sorted by score, highest first; ties go to the id seen first, across
  all lists in order.
- `k < 0` raises `ValueError("k must be >= 0")`.
- Empty input gives `[]`.

Example: `rrf_merge([["a","b"],["b","c"]], k=0)` gives
`[('b', 1.5), ('a', 1.0), ('c', 0.5)]`.

Ranks are fused, not scores, so BM25 and cosine never need the same scale.

## `bm25.py`: keyword search, every term visible

`BM25Index(docs, k1=1.5, b=0.75)` takes a list of texts, each tokenized with
`rag.text.tokenize`. It keeps term counts per doc, doc lengths and `avgdl`, plus two
idf values:

- `idf(t) = ln(1 + (n − df + 0.5)/(df + 0.5))`;
- `unseen_idf = ln(1 + (n + 0.5)/0.5)`, used for a term no document contains.

- `scores(query, allowed=None) -> dict[int, float]`:
  - Uses the set of `tokenize(query, expand=True)`.
  - The standard BM25 sum is `idf · f·(k1+1) / (f + k1·(1 − b + b·len/avgdl))`.
  - Only docs in `allowed` are scored when it is not `None`; an empty set scores
    nothing and returns `{}`.
  - Only scores above 0 are returned.
- `max_possible(query) -> float`:
  - It is `Σ idf(t)·(k1+1)` over the expanded query terms, with `unseen_idf` for terms
    the corpus has never seen, or 1.0 if that sum is 0.
  - The retriever divides by it to get keyword coverage. Unseen terms count at full
    weight, so "pasta recipes" looks poorly covered.

## `chunking.py`: chunks that cite exactly one section

Constants: `MAX_WORDS = 220` and `MIN_WORDS = 60`.

**`chunk_section(meta, section, used=None) -> list[Chunk]`**

1. **Split long paragraphs.** A paragraph over `MAX_WORDS` is split at sentence ends,
   using the regex `(?<=[.;:])\s+(?=[A-Z(])`. The pieces are packed into parts of at
   most `MAX_WORDS`, and each part keeps the paragraph's label.
2. **Group the paragraphs in order.** Sizes count words of the paragraph **text only**
   (`len(p.text.split())`), never the label. Start a new chunk before paragraph `p`:
   - when the current chunk's words plus `p`'s would exceed `MAX_WORDS`; or
   - when `p`'s top-level label differs from the **previous paragraph's** top-level label
     and the current chunk already has at least `MIN_WORDS`.

   The top level of a label is the part up to its first `)` when it starts with `(`
   (`(b)(2)` → `(b)`), else the part before the first `.` (`4.2` → `4`). An empty label's
   top level is `""`, so it differs from `(b)`.

   **Check:** `uv run underwriter ingest` must report **664 chunks from 11 documents**.
   673 means labels were counted as words.
3. **Fill the chunk fields.**
   - Text is `"<label> <text>"` joined with spaces, then stripped.
   - `first_label` is the first paragraph's label.
   - `doc_id`, `section_id`, `heading`, `title`, `source_type` and `status` come from
     `meta` and `section`.
4. **Build the id.** It is `f"{doc_id}#{section_id}{first_label if first_label.startswith('(') else ''}"`,
   e.g. `reg-b-12cfr1002#1002.9(b)(2)` or `mdl-upl-policy-3.2#4`.
   - When an id repeats, the second gets `~1`, the third `~2`, and so on.
   - `used` (a dict shared across one document) keeps ids unique.
5. **Build the citation.** Rules in order; the first match wins. `sid` is
   `section.section_id`:

   | Case | Citation |
   |---|---|
   | `source_type == "internal_policy"` | `MDL policy §{sid} {heading}` |
   | `sid` starts with `Supplement I to Part 1002` | `12 CFR 1002 Supp. I, {rest or heading}`, where `rest` is `sid` with that prefix removed and stripped |
   | `sid` starts with `Appendix` and doc is `reg-b*` | `12 CFR 1002, {sid without " to Part 1002"}` |
   | `sid` starts with `Appendix-` and doc is `ftc-*` | `16 CFR 681, Appendix {part after "-"}{first_label}` |
   | format xml/html and `sid` fully matches `\d+\.\d+` (like `1002.9`) | `{prefix} {sid}{first_label}`; the prefix is `12 CFR` when `doc_id` starts with `reg-b` or `reg-z`, `16 CFR` for `ftc-`, `31 CFR` for `cip-`, else `CFR` |
   | anything else | `{title before the first ":"}, {sid}` |

**`chunk_document(meta, sections)`** chunks every section with one shared `used` dict.

## `retriever.py`: filter first, then hybrid search, then abstain

Constants:
- `DATA_DIR` is the repo's `data/`;
- `TODAY = date(2026, 10, 22)`, fixed so the course behaves the same every year;
- `MIN_BM25_COVERAGE = 0.14` and `MIN_COSINE = 0.17`, set from the eval.

- `load_manifest(data_dir=DATA_DIR)` turns `data/corpus/manifest.json` `documents`
  into a list of `DocumentMeta`.
- `in_force(meta, docs, on)` returns False in three cases:
  - `in_force_from` is after `on`;
  - `withdrawn_on <= on`;
  - its `superseded_by` successor's `in_force_from` (or, if unset, its
    `effective_date`) is `<= on`.

  Otherwise it returns True.
- `PolicyIndex(docs, data_dir=DATA_DIR, embedder=None)`:
  - Exposes `docs` (a dict by `doc_id`), `chunks` (a list), `embedder`, `bm25` and
    `vectors`; the CLI and the tests read `chunks`, `docs[...]` and `embedder.name`.
  - Chunks every document with `parse_document` and then `chunk_document`.
  - Indexes `f"{heading} {text}"` per chunk in BM25, and embeds the same text
    (`HashingEmbedder` by default).
  - `stats()` gives the chunk count per `doc_id`, in chunk order.
- `default_index()` is one cached `PolicyIndex(load_manifest())`.
- `PolicyRetriever(index=None, candidates=50)` (`index=None` means `default_index()`), with
  `retrieve(query, k=5, as_of=None, include_withdrawn=False, source_types=None) -> RetrievalResult`:
  1. **Pre-filter** to chunks of documents in force on `as_of` (default `TODAY`).
     Skip this filter when `include_withdrawn` is set. Also keep only `source_types`,
     when given. A withdrawn document must never be a candidate.
  2. **Search:** BM25 top `candidates`, and cosine top `candidates`, both over the
     allowed chunks only.
  3. **Fuse:** `rrf_merge` the two id lists, and take the first `k` as `RetrievedChunk`s
     with these fields:
     - `chunk`, the fused `score` (rounded to 5 places);
     - `bm25` and `cosine` (3 places);
     - `bm25_rank` and `vector_rank`.
  4. **Abstain** when either measure is too low:
     - keyword coverage (best BM25 score / `max_possible(query)`) is below
       `MIN_BM25_COVERAGE`;
     - or the best cosine is below `MIN_COSINE`.

     The result then has `abstained=True`, `results=[]`, and the reason
     `f"No applicable policy found (keyword coverage {coverage:.2f}, best similarity {best_cos:.2f})"`.
     Coverage is 0.0 when no chunk scored. Otherwise `abstained=False`.

     Cosine is computed for every allowed chunk, not just the top `candidates`. Ranks are
     1-based, and a chunk missing from one list has that rank `None` and `bm25` 0.0.

## Changes to earlier modules

None. (The given `rag/analyzer.py` is what the workflow uses to call your retriever.)

<!-- api:start -->

## Public API

### `src/underwriter/rag/chunking.py`

Imported elsewhere (keep these names exactly): `MAX_WORDS`

Builds on: `underwriter.rag.models`

- constant `MAX_WORDS = 220`
- constant `MIN_WORDS = 60`
- function `chunk_section(meta: DocumentMeta, section: Section, used: dict[str, int] | None=None) -> list[Chunk]`
- function `chunk_document(meta: DocumentMeta, sections: list[Section]) -> list[Chunk]`

### `src/underwriter/rag/bm25.py`

Builds on: `underwriter.rag.text`

- class `BM25Index`
  - method `__init__(self, docs: list[str], k1: float=1.5, b: float=0.75) -> None`
  - method `scores(self, query: str, allowed: set[int] | None=None) -> dict[int, float]`
  - method `max_possible(self, query: str) -> float`
    > Upper bound used to normalise scores for the abstain decision.
    >
    > Query terms the corpus has never seen count at full weight: a question about
    > "pasta recipes" should look poorly covered, not well covered by "fresh".

### `src/underwriter/rag/fusion.py`

Imported elsewhere (keep these names exactly): `rrf_merge`

- function `rrf_merge(rankings: list[list[str]], k: int=60) -> list[tuple[str, float]]`
  > Merge ranked lists of ids into one ranking.
  >
  > Each id scores Σ 1 / (k + rank) over the lists it appears in (rank starts at 1).
  > Ranks, not raw scores, are combined, so BM25 scores and cosine similarities never
  > need to be on the same scale. Ties are broken by first appearance, so the result
  > is deterministic.
  >
  > >>> rrf_merge([["a", "b"], ["b", "c"]], k=0)
  > [('b', 1.5), ('a', 1.0), ('c', 0.5)]

### `src/underwriter/rag/retriever.py`

Imported elsewhere (keep these names exactly): `DATA_DIR`, `PolicyRetriever`, `default_index`, `in_force`, `load_manifest`

Builds on: `underwriter.rag.bm25`, `underwriter.rag.chunking`, `underwriter.rag.embedding`, `underwriter.rag.fusion`, `underwriter.rag.models`, `underwriter.rag.parsers`

- constant `DATA_DIR = Path(__file__).resolve().parents[3] / 'data'`
- constant `TODAY = date(2026, 10, 22)`
- constant `MIN_BM25_COVERAGE = 0.14`
- constant `MIN_COSINE = 0.17`
- function `load_manifest(data_dir: Path=DATA_DIR) -> list[DocumentMeta]`
- function `in_force(meta: DocumentMeta, docs: dict[str, DocumentMeta], on: date) -> bool`
  > Is this document the applicable version on date `on`?
- class `PolicyIndex`
  > All chunks of the corpus, with a BM25 index and a vector per chunk.
  - method `__init__(self, docs: list[DocumentMeta], data_dir: Path=DATA_DIR, embedder: Embedder | None=None) -> None`
  - method `stats(self) -> dict[str, int]`
- function `default_index() -> PolicyIndex`
- class `PolicyRetriever`
  - method `__init__(self, index: PolicyIndex | None=None, candidates: int=50) -> None`
  - method `retrieve(self, query: str, k: int=5, as_of: date | None=None, include_withdrawn: bool=False, source_types: set[str] | None=None) -> RetrievalResult`

<!-- api:end -->
