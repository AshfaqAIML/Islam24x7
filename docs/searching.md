# Full-text search

Keyword and phrase search over the whole knowledge base — book catalog
titles/names, normalized chunk content, Quran (Arabic ayahs and their
translations) and hadith (English text + Arabic original). Every hit is
traceable back to its source: book, chapter/section, page, and the chunk
document that matched.

## Domains

| Domain | What matches | Backend |
| ------ | ------------ | ------- |
| `book` | book `title`/`subtitle` + author name | `pg_trgm` similarity over catalog |
| `chapter` / `section` | chapter / section titles | `pg_trgm` similarity over catalog |
| `content` | normalized chunk text + book title | `tsvector` (`search_documents`) |
| `quran` | Arabic ayah text and ayah translations | `tsvector` (`ayahs`/`ayah_translations`) |
| `hadith` | hadith English text and Arabic original | `tsvector` (`hadiths`) |

## Query syntax

Input is the usual web-search syntax, normalized with the same rules the
indexing pipeline applied to the stored text:

- `prayer` — a keyword; several keywords match **any** of them (`OR`).
- `prayer sunnah` with `--all-terms` — every keyword must appear (**AND**).
- `"the prayer"` — a verbatim **exact phrase** (double quotes).
- Phrases are ANDed with any keyword parts.

Language is sniffed from the query text (Arabic/Urdu script vs. Latin) so
normalization matches how the content was indexed; the query is always run
with the `simple` text-search configuration, because every document vector
carries a verbatim `simple` component.

## CLI

```pwsh
knowledge-base index run --sha256 8e3ba214de62          # index one book
knowledge-base index run --all --limit 10               # capped batch

knowledge-base search "the prayer"
knowledge-base search 'السلام عليكم' --language ar
knowledge-base search "tadhkirah" --book 8e3ba21 --author "ibn mulaqqin"
knowledge-base search "quran" --domains content quran --all-terms --limit 5
knowledge-base search "fiqh" --category fiqh --json
```

Filters: `--domains` (one or more of the six domains), `--all-terms`,
`--language ar|ur|en`, `--category <code>`, `--book <sha256 prefix>`,
`--author <substring>`, `--limit`, `--json`.

Results rank by relevance across all requested domains (per-domain on
`ts_rank_cd` for tsvector, `similarity()` for trigram) and print
`Book:`/`Chapter:`/`Page:`/`Matched:` plus the chunk citation; `--json` dumps
the full `SearchHit` records.

## Indexing flow

1. The **chunk** stage must have run: `content_chunks` rows exist for the book.
2. `index` reads the book's chunks, deletes its existing `search_documents`
   rows, and inserts one `document_type='chunk'` row per chunk — `language`
   from the book, `title` = book title, `body_text` = chunk text.
3. PostgreSQL triggers populate and keep in sync the `search_vector` columns
   (also on `ayahs`, `ayah_translations`, `hadiths` on insert/update).
4. A `ProcessingJob(job_type=INDEX)` records the run (idempotent) with a
   `.txt` report under `data/processed/index/<sha256>.txt`.

Re-running a book's index (or re-chunking it) is safe: the FK from
`search_documents → content_chunks` is `ON DELETE CASCADE`, so stale
documents disappear with their chunks.

## Invariants

- Vectors can never drift: they are written by database triggers from the
  stored text, not by application code, and backfilled for existing rows at
  migration time.
- Indexing is idempotent — the same book produces the same document count and
  a single `INDEX` job record.
- A book with no chunks yields a **failed** `INDEX` job ("did the chunk stage
  run?"), never partial documents.
- Queries normalize identically to indexing, so Arabic/Urdu/English text
  matches its own language consistently; exact phrases match only when the
  tokens appear in order in the same document.