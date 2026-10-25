# Lesson 2 — Enterprise RAG: the Credit Policy Intelligence Service

> Retrieval that is right about *which version of the rule applies* matters more than
> retrieval that is clever.

**Slides:** [PDF](slides/lesson-02-rag.pdf)
**Duration:** 3 hours (80 min concepts + walkthrough, 100 min lab)
**Code at end of lesson:** `solution/lesson-02/` in the course repo

## Objectives

By the end of this lesson students can:

1. Parse real regulatory documents in three formats (eCFR XML, HTML, Federal Register PDF) into labelled sections.
2. Chunk without crossing section boundaries, and cite every chunk precisely (`12 CFR 1002.9(b)(2)`).
3. Build hybrid retrieval: BM25 keyword search plus vector search, merged with reciprocal rank fusion.
4. Filter *before* ranking, so withdrawn and superseded documents can't be cited by accident.
5. Make the retriever abstain ("no applicable policy found") instead of returning its best guess.
6. Measure retrieval with an eval (hit@5, MRR, abstain accuracy, stale citations) and set thresholds from data.

## The corpus

`data/corpus/manifest.json` lists 11 documents: our fictional lender's internal policy,
plus 10 real US federal documents (public domain). Three are traps:

| Trap | What a naive retriever does | What ours does |
|---|---|---|
| Reg Z §1026.43 **as of 2020** says DTI must "not exceed 43 percent" (§1026.43(e)(2)(vi)); the current rule replaced that with a price test in 2021 | Cites the 43% limit as current law | Returns the current rule today; the 2020 text only with `--as-of 2020-06-01` |
| CFPB Circulars 2022-03 and 2023-03 (adverse action and complex algorithms) were **withdrawn on 2025-05-12** | Cites them, because they are the best keyword match for "AI denials" | Excludes them by default and falls back to Regulation B itself |
| The SR 26-2 "letter" PDF **repeats the whole attachment** | Indexes everything twice | The manifest ingests the cover pages only |

## Agenda

| Time | Block |
|---|---|
| 0:00 | Why the lender's policy alone isn't enough: regulation, guidance, versions |
| 0:15 | Parsing: what each format keeps and loses (`rag/parsers.py`) |
| 0:30 | Chunking and citations (`rag/chunking.py`) |
| 0:45 | Hybrid search: BM25, vectors, RRF (`rag/bm25.py`, `rag/embedding.py`, `rag/fusion.py`) |
| 1:00 | Filter first, then rank; abstain (`rag/retriever.py`) |
| 1:10 | Measuring retrieval (`evaluation/retrieval.py`, `evals/retrieval_cases.json`) |
| 1:20 | Break |
| 1:30 | Lab: exercises 1–3 |
| 2:50 | Debrief: what would change with a real embedding model? |

## Setup

```bash
cd solution/lesson-02          # in the course repo (START-HERE.md)
uv sync --all-groups
uv run underwriter ingest          # 664 chunks from 11 documents
uv run underwriter eval-retrieval  # 20/20 cases pass
```

No API key and no database: the index is built in memory in about 2 seconds.

## Walkthrough

```bash
uv run underwriter search "Applicant DTI = 46%. What policy applies?"
uv run underwriter search "maximum debt-to-income ratio for a qualified mortgage"
uv run underwriter search "maximum debt-to-income ratio for a qualified mortgage" --as-of 2020-06-01
uv run underwriter search "explaining credit denials made by complex algorithms"
uv run underwriter search "explaining credit denials made by complex algorithms" --include-withdrawn
uv run underwriter search "best pasta recipe"
uv run underwriter run data/applications/APP-002.json   # note the policy_retrieval step
```

Things to point at:

1. **`parsers.py` → `_LabelPath`**: eCFR XML labels each paragraph with only its own level (`(4)`). Citations need the full path (`(c)(4)`), so the parser rebuilds it. A paragraph can also open a deeper level mid-sentence: "(a) Notification—(1) When notification is required."
2. **`parsers.py` → `_extract_pdf_text`**: a Federal Register page holds several agencies' rules. We cut our document at its own `[FR Doc. …]` line.
3. **`chunking.py`**: never cross a section; prefer breaking at a top-level paragraph; cap at 220 words.
4. **`retriever.py` → `_allowed` and `in_force`**: the filter runs *before* ranking. Post-filtering would let a withdrawn circular take a top-5 slot, then drop it, leaving 4 results.
5. **`retriever.py` abstain rule**: two signals, keyword coverage (with unseen words counted against it) and best cosine. Thresholds sit between the answerable and must-abstain groups in the eval.
6. **`rag/analyzer.py`**: the workflow now cites retrieved chunks (`mdl-upl-policy-3.2#4`), but decisions still come from `decision/engine.py`. Retrieval explains; the engine decides.

### Results at the end of the lesson

```text
hit@5 1.00 · MRR 0.89 · abstain accuracy 1.00 · stale citations 0 · 20/20 cases pass
```

Be honest with the class about two weaknesses the eval shows:

- **R05 ranks the 43% paragraph 5th**, not 1st. Keyword and hashed vectors both see "debt", "income", "ratio" in many paragraphs.
- **The abstain margins are thin** (answerable coverage ≥ 0.19 vs off-topic ≤ 0.09). Twenty cases is a start, not a validation set.

## Lab exercises

### Exercise 1: Write `rrf_merge` (30 min)

Replace the body of `rrf_merge` in `src/underwriter/rag/fusion.py` with `raise NotImplementedError`, then make `tests/test_rag_fusion.py` pass from the docstring alone. Then answer: why combine *ranks* rather than BM25 scores and cosines directly?

**Acceptance:** `uv run pytest tests/test_rag_fusion.py` green; `eval-retrieval` still 20/20.

### Exercise 2: Grow the eval and defend your thresholds (40 min)

Add five cases to `evals/retrieval_cases.json`: three answerable ones you verified by reading the source, one `as_of` case and one `must_abstain`. Run the eval. If anything fails, decide whether the retriever, the threshold or your expectation is wrong, and write one paragraph saying which and why.

### Exercise 3: Chunk size experiment (30 min)

Run the eval with `MAX_WORDS` at 120, 220 and 400 and record hit@5 and MRR in a table. Which would you ship, and what would you watch for in production?

**Stretch:** after lesson 3, implement an `Embedder` backed by a real embedding model through the LLM port and compare the eval.

## Homework / deliverable

PR containing:

- [ ] Exercise 1 (your `rrf_merge`, tests green)
- [ ] Exercise 2 cases plus your threshold paragraph
- [ ] Exercise 3 results table and recommendation

## Rubric

| Criterion | Strong | Weak |
|---|---|---|
| Eval cases | Expected sources found by reading the document | Copied from retriever output |
| Versioning | Explains why filtering happens before ranking | "We filter out old docs" |
| Abstain | Threshold justified from both groups' scores | Picked a round number |
| Citations | Every answer points to a paragraph a reviewer can open | Document-level only |

## Interview questions this lesson prepares for

- Design a RAG pipeline for regulatory documents. How do you handle document versions?
- Pre-filter vs post-filter: when does each fail?
- Why hybrid search? When does BM25 beat embeddings?
- How do you know retrieval is good enough to ship? What do you measure?
- How do you stop a RAG system from answering when it has nothing relevant?

