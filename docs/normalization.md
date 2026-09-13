# Normalization pipeline

Derives a **search-normalized variant** of every body paragraph of a published
book and stores it separately in `normalized_texts`. The source of truth is
always `content_blocks.original_text`, which this stage **never modifies** —
each row records the SHA-256 of the original it was derived from, so a later
reader can prove the provenance held.

The `normalize_text` core and its configuration live in
`src/knowledge_base/normalization/` (pure functions, committed earlier); this
stage adds the database materialization.

## Flow

1. Select the book by source `sha256` (or all published books with `--all`).
2. Load its `content_blocks` in page order.
3. Skip every non-`PARAGRAPH` block type. Verse, hadith, reference, footnote,
   heading, front matter, TOC entries etc. are never folded or rewritten —
   religious/structural content stays byte-identical by construction.
4. Pick a config (see below) and run `normalize_text` per paragraph.
5. Rewrite the book's `normalized_texts` rows (delete + reinsert, idempotent)
   and record a `ProcessingJob(job_type=NORMALIZE)` manifest + a `.txt`
   report under `data/processed/normalized/<sha256>.txt`.

## Config selection (default `auto`)

| Book language | Config | Effect |
| ------------- | ------ | ------ |
| **Arabic** (`ar`) | `search` | NFC, whitespace/linebreak collapse, tatweel removal, hamza/alef folding (standard Arabic search fold), digit normalization |
| **Urdu** (`ur`) | `urdu` | NFC + whitespace + digits normalized (Arabic-Indic/Urdu numerals -> ASCII) so digit variants match; **Urdu letters are never folded** |
| **English** / other | `conservative` | NFC + whitespace/linebreak collapse + tatweel removal only — no character folding at all |

`--config conservative|search` overrides the language default for every book
in the run.

## Religious-content protection

`NormalizationConfig` skips **all character-level folding** whenever the text
contains a protected marker (`protect_religious_quotations=True`). Markers
include the basmala ligature (U+FDF2), Quranic ornaments (U+FD3F/U+FD3E),
`ﷺ`/`ﷻ` ligatures, and common phrases; protected rows are flagged
(`protected = true`) and their variant is byte-identical to the original.
Protection is per-block: layout-only cleanup (NFC, whitespace) still applies.

## Invariants (under test)

- `content_blocks.original_text` is byte-identical after a run, for every
  block type (see `tests/test_normalize_pipeline.py`).
- `original_sha256 == sha256(original_text)` on every row.
- Protected blocks: `normalized_text == original_text`.
- Non-`PARAGRAPH` blocks produce no `normalized_texts` row.
- Re-running is idempotent: same row count, no duplicates, same originals.
- Deleting a `content_block` (e.g. structure re-run) cascades to its
  `normalized_texts` row (FK `ON DELETE CASCADE`).

## CLI

```pwsh
knowledge-base normalize run --sha256 8e3ba214de62            # one book
knowledge-base normalize run --all                            # every published book
knowledge-base normalize run --sha256 ... --config conservative  # override
knowledge-base normalize file some.txt --config search        # file utility
```

The `normalize file` subcommand keeps the original file-report utility (writes
`data/processed/normalized/<source_id>.json|.md`) and takes no database
connection.