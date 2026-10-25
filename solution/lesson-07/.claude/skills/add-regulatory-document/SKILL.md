---
name: add-regulatory-document
description: Add a real public regulatory or guidance document to the retrieval corpus (manifest entry, checksum, in-force dates, parsing, a retrieval eval case). Use when the agent must cite a regulation, rule or guidance the corpus doesn't have yet.
---

# Add a document to the corpus

The corpus is real US federal text with checksums. A document that's in it but not in
force on the decision date must never be cited.

1. **Pick the authoritative source:** eCFR XML for a regulation, the Federal Register
   for a rule or notice, the agency's page for guidance. Note why it's needed
   (`why_included`).
2. **Add a manifest entry** in `data/corpus/manifest.json` with these fields:
   - `doc_id`, `title`, `issuer`, `source_type`, `format` (`xml`, `html`, `pdf` or `md`);
   - `path` under `data/corpus/raw/`, `url`, `effective_date`, `status`, `why_included`;
   - the dates (rules in `date_semantics` at the top of the file): `in_force_from` when
     it matters, and `withdrawn_on` / `withdrawn_by` or `superseded_by` / `supersedes`
     when one version replaces another.
3. **Fetch it:** `python scripts/fetch_corpus.py`, which records `sha256` and `bytes`.
   Don't edit downloaded files: the checksum is how a changed source gets noticed.
4. **Parse it:** `uv run underwriter ingest` and check the chunk count for the new
   `doc_id`. If the parser needs a change for this format, make it in `rag/parsers.py`
   with a test in `tests/test_rag_parsing.py`. Each chunk must cite exactly one section.
5. **Prove retrieval finds it:** add at least one case with `add-retrieval-case`, and an
   `as_of` case if versions overlap.
6. **Verify:** `uv run underwriter eval-retrieval` must still pass every case, with 0
   stale citations; then `/verify`.

<rules>
- Public sources only, with their licence or public-domain status noted in
  `license_note` when it isn't federal text.
- Never cite a withdrawn or superseded version for a current decision; that is what
  `in_force` and the as-of cases protect.
</rules>
