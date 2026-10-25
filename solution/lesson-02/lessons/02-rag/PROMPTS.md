# Lesson 2 prompt pack: build hybrid retrieval with Claude Code

You build four modules in `src/underwriter/rag/` from `SPEC.md`. The parsers, the
embedder, the models and the corpus are given: format quirks of eCFR XML and Federal
Register PDFs aren't the point of the lesson.

```bash
cd ~/fde-work/lesson-02        # your copy of starter/lesson-02 (START-HERE.md)
uv sync --all-groups
uv run pytest --continue-on-collection-errors     # red: fusion, bm25, chunking, retriever
claude
```

`tests/test_rag_parsing.py` and `tests/test_rag_retriever.py` build the index when
they're imported, so they error at collection until chunking and the index work (step
3). Run one test file at a time until then.

```text
/start-lesson 02
```

## 1. Clarify and plan (10 min)

```text
/plan-lesson 02
```

The plan must go bottom-up: fusion and BM25 (pure functions), then chunking, then the
retriever. Reject a plan that starts with `retrieve`.

Then scaffold the interfaces (5 min). Test files import names from several of this
lesson's modules at the top, so until every name exists each file errors at import and
the per-step test commands below can't run. The scaffold makes each test fail on its own.
Skip it only if you'll write every module before running any test:

```text
<task>Scaffold the public API of lesson 02's modules</task>
<spec>lessons/02-rag/SPEC.md, the "Public API" section</spec>
<method>In each module SPEC.md lists, keep the module docstring and add every public name
with its exact signature and docstring, and a body of `raise NotImplementedError`.
Constants get their values; classes get their fields and method stubs; constructors
(`__init__`) just store their arguments, as SPEC.md lists them.</method>
<tests>uv run pytest --continue-on-collection-errors</tests>
<done_when>The tests now fail one by one (NotImplementedError) rather than at import, and
ruff is clean. No logic yet.</done_when>
```

## 2. Fusion and BM25 (20 min)

```text
<task>Build src/underwriter/rag/fusion.py, then src/underwriter/rag/bm25.py</task>
<spec>lessons/02-rag/SPEC.md, sections "fusion.py" and "bm25.py"</spec>
<tests>uv run pytest tests/test_rag_fusion.py</tests>
<constraints>No library for BM25 or fusion: every term visible. Use rag.text.tokenize
(expand=True for queries). Don't edit tests/.</constraints>
<done_when>The fusion tests pass, BM25 matches the formula in SPEC.md, and ruff is clean.</done_when>
```

Ask Claude, and put both answers in your PR in your own words:
- Why fuse ranks and not scores?
- What does `b` do to a long Reg B section?

## 3. Chunking and the index (25 min)

```text
<task>Build src/underwriter/rag/chunking.py (chunk_section, chunk_document), then the index
half of src/underwriter/rag/retriever.py: the constants, load_manifest, in_force,
PolicyIndex and default_index</task>
<spec>lessons/02-rag/SPEC.md, sections "chunking.py" (grouping rules, id scheme, citation
table, exactly) and "retriever.py" (everything except retrieve)</spec>
<tests>uv run pytest tests/test_rag_parsing.py -q, then uv run underwriter ingest and
uv run pytest tests/test_rag_retriever.py -k in_force_rules</tests>
<constraints>Never cross a section boundary. Ids unique per document. The citation strings
are checked by the retrieval eval, so follow the table.</constraints>
<done_when>The parsing tests and the in-force test pass, and ingest reports 664 chunks from 11 documents.</done_when>
```

The chunking tests need the index (`default_index()`), which is why the index is built
in the same step.

## 4. Retrieve, with abstain (20 min)

```text
<task>Build PolicyRetriever.retrieve in src/underwriter/rag/retriever.py</task>
<spec>lessons/02-rag/SPEC.md, section "retriever.py", steps 1–4 of retrieve</spec>
<tests>uv run pytest tests/test_rag_retriever.py -q, then uv run underwriter eval-retrieval</tests>
<constraints>Filter first, then rank: a withdrawn document is never a candidate. Keep
MIN_BM25_COVERAGE and MIN_COSINE exactly as SPEC.md gives them.</constraints>
<done_when>eval-retrieval passes all 20 cases with 0 stale citations, and the whole suite is green.</done_when>
```

If a case fails, don't let Claude move the thresholds. Ask it which case fails and why,
then decide yourself (`debug-root-cause`).

## 5. Verify, review, learn (10 min)

```text
/verify
/review
/learn <anything worth keeping>
```

## Done when

- `uv run pytest` and `eval-retrieval` (20/20, 0 stale citations) are green.
- `uv run underwriter search "maximum DTI for a qualified mortgage"` cites the current
  rule, and the same query with `--as-of 2020-06-01` cites the 2020 text.
- Your PR explains filter-then-rank in two sentences.

## Don't delegate

The abstain thresholds, and the expected sources for any eval case you add
(`add-retrieval-case`). Those come from reading the documents.
