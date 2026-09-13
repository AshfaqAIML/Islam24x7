# Chunking pipeline

Splits a published book's paragraphs into retrieval-ready **chunks** so a
downstream search/embedding stage can index coherent, structure-aware units
instead of page slices or arbitrary fixed-length windows.

## What a chunk is

One `content_chunks` row groups **consecutive paragraphs** that share a
(chapter, section) and fit a token budget. Every chunk preserves full
provenance:

- `source_file_id`, `book_id`, `chapter_id`/`chapter_no`, `section_id`/`section_no`
- `content_block_id` (first block) and `metadata_["block_ids"]` (all blocks)
- `page_start`/`page_end`, `token_count`, `language`, `sequence` (chunk order)
- `text`, `is_normalized`, `status` (`PENDING`)

Chunk text is the **search-normalized variant** of each paragraph where the
normalization stage produced one, joined with `\n\n`; blocks without a
normalized variant fall back to `content_blocks.original_text`. Chunking
**never modifies** the source blocks or the normalization rows.

## Rules (under test)

- Paragraphs are atomic: a paragraph larger than the budget becomes a chunk by
  itself, never a fragment.
- A chunk never spans two sections or chapters.
- Overlap repeats only **whole paragraphs** from the tail of the previous
  chunk and never bleeds across a section boundary.
- Deterministic stable ids:
  `sha256(source_sha:chapter_no:section_no:first_page:chunk_index)` (64 hex).
- Idempotent: re-running a book deletes + reinserts its chunks with the same
  ids and count.
- Books with no detected structure degrade gracefully: everything groups into
  one continuous (NULL, NULL) region with page spans retained.

## Flow

1. Select the book by source `sha256` (or all published books with `--all`,
   capped by `--limit`).
2. Load `content_blocks` of type `PARAGRAPH` in (page, sequence) order, joining
   their page / chapter / section numbers.
3. For each paragraph pick the normalized variant if present, else the original.
4. Estimate tokens per paragraph (script-aware: ~3 chars/token for Arabic/Urdu,
   ~4 otherwise) and group with `ChunkConfig(max_tokens, overlap_tokens)`.
5. Rewrite the book's `content_chunks` rows (delete + reinsert, idempotent) and
   record a `ProcessingJob(job_type=CHUNK)` manifest + `.txt` report under
   `data/processed/chunk/<sha256>.txt`.

Configuration lives in `src/knowledge_base/pipeline/chunk/config.py` (default
`max_tokens=512`, `overlap_tokens=64`; overlap must stay below max).

## CLI

```pwsh
knowledge-base chunk run --sha256 8e3ba214de62              # one book
knowledge-base chunk run --all --limit 10                   # capped batch
knowledge-base chunk run --sha256 ... --max-tokens 256 --overlap 32
```

## Invariants

- Original blocks and `normalized_texts` rows are byte-identical after a run.
- `token_count` equals the sum of per-paragraph estimates plus `\n\n`
  separators (never a post-hoc re-estimate of the joined text).
- Re-running is idempotent: same chunk ids, same count, no duplicates.
- Deleting a book cascades to its `content_chunks` rows (FK → `books.id`).
  During a re-chunk the pipeline deletes + reinserts a book's own rows, so block
  provenance inside `metadata_["block_ids"]` is refreshed on every run.