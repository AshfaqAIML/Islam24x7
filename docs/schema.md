# Database Schema

**Status:** Implemented (migration `20441164e13e_initial_schema`).

PostgreSQL 18 + pgvector container (`islam24x7-db`, host port `5434`).
Migrations live in `src/knowledge_base/database/migrations/`; ORM models in
`src/knowledge_base/database/models/`.

All tables:
- use a stable UUID v4 primary key (`id`),
- carry server-managed `created_at` / `updated_at` (UTC, timezone-aware),
- never store binary content — only the SHA-256 provenance chain.

## Domain overview

```
sources        source_files → source_editions → books
                 ├── licenses
                 └── processing_jobs
books          categories / authors / publishers / translators / topics
structure      books → chapters (kind) → sections → subsections
                 └─ pages → paragraphs → content_blocks → content_chunks
quran          surahs → ayahs → ayah_translations
hadith         hadith_collections → hadith_books/hadith_chapters → hadiths
search         content_chunks → search_documents (tsvector + GIN)
embeddings     embedding_models → embeddings (vector + HNSW)
```

## Sources domain

### `source_files`
The content-addressed root of every pipeline run.

| Column | Type | Constraint / note |
| ------ | ---- | ----------------- |
| `sha256` | `text` | `UNIQUE` — stable content identity |
| `file_path` | `text` | path under `data/raw/` |
| `format` | enum `kb_sourceformat` | `pdf`, `epub`, `docx`, `txt`, `html`, `json` |
| `size_bytes` | `int` | nullable |
| `status` | enum `kb_sourcestatus` | default `registered` |
| `title_hint` / `language_hint` | `text` / `varchar(16)` | nullable, pre-inspection |

### `source_editions`
One edition per source file (physical file == one printed edition).

| Column | Type | Note |
| ------ | ---- | ---- |
| `source_file_id` | FK → `source_files` | `UNIQUE` (1:1) |
| `title`, `subtitle` | `text` | `subtitle` nullable |
| `language` | `varchar(16)` | e.g. `ar`, `ur`, `en` |
| `publisher`, `publication_year`, `isbn`, `notes` | — | `isbn` `UNIQUE` when set |

### `licenses`
Copyright/distribution record. `UNIQUE (source_file_id, license_type)`;
`license_type` enum `kb_licensetype`, with `holder`, `granted_at`, `expiry_at`, `rights`.

### `processing_jobs`
Idempotent stage tracking. `UNIQUE (source_file_id, job_type)` makes each
pipeline stage a single record per file (re-run replaces in place).
`job_type` enum `kb_jobtype`, `status` enum `kb_jobstatus`, `manifest` JSONB.

### `ocr_pages`
Per-page OCR output for scanned and mixed PDFs (migration
`75a57d77d004_add_ocr_results`). One row per `(source_file_id, page_number)`:

| Column | Type | Note |
| ------ | ---- | ---- |
| `engine` | `text` | engine used, e.g. `tesseract` / `easyocr` / `dummy` |
| `engine_version` | `text` | nullable engine version string |
| `languages` | `text` | comma-joined training languages |
| `status` | enum `kb_ocrstatus` | `ok` / `review` / `failed` |
| `confidence` | `float` | nullable per-page engine confidence |
| `text_chars` | `int` | recognized text length |
| `quality_notes` | `text` | comma-joined review flags, e.g. `low_confidence` |
| `text_path` / `image_path` | `text` | relative paths under `data/processed/ocr/<sha>/` |

### `metadata_candidates`
Extracted-but-unverified book metadata (migration
`44d8e71f7328_add_metadata_candidates`). One row per distinct
`(source_file_id, field, source, value)` — the dedupe key repeats on every
extraction so review decisions survive re-runs. Never imported into
`books`/`source_editions` without an explicit human `approve` + `publish`.

| Column | Type | Note |
| ------ | ---- | ---- |
| `field` | enum `kb_metadatafield` | `title`, `subtitle`, `author`, `translator`, `editor`, `publisher`, `publication_year`, `edition`, `language`, `isbn`, `category`, `description`, `page_count` |
| `value` | `text` | candidate value (verbatim, cleaned) |
| `confidence` | enum `kb_metadataconfidence` | `high` / `medium` / `low` |
| `uncertain` | `bool` | flagged for human review; uncertain candidates are never auto-published |
| `source` | enum `kb_metadatasource` | `pdf_metadata` / `filename` / `first_pages` / `title_page` / `user_provided` |
| `evidence` | `text` | where the value came from (page/line, marker, method) |
| `status` | enum `kb_metadatareviewstatus` | `pending` / `review` / `approved` / `rejected` |
| `review_note` / `reviewed_at` / `reviewed_by` | — | human review audit trail |

`user_provided` candidates are written as `approved` (reviewed_by `operator`)
but still require the `publish` step. See `docs/metadata.md` for the flow.

## Books domain

| Table | Notable columns |
| ----- | --------------- |
| `books` | `title`, `subtitle`, `language`; FKs → `source_file` (NOT NULL), `edition`, `author`, `translator`, `publisher`, `category` |
| `categories` | `code` `UNIQUE`, `name`, `parent_id` (self-FK) |
| `authors` | `name` `UNIQUE`, `name_arabic`, `bio` |
| `translators` | `name` `UNIQUE`, `name_arabic` |
| `publishers` | `name` `UNIQUE`, `city`, `country` |
| `topics` | `name` `UNIQUE`, `category_id` |
| `book_topics` | association: `book_id` + `topic_id` `UNIQUE` pair |

Every `book` resolves bidirectionally to its raw source file
(`books.source_file_id`), so even catalog metadata is provenance-bound.

## Structure domain (book internals)

Migration `f7e2c9a1b3d4_add_structure_detection`.

| Table | Notable columns / constraints |
| ----- | ----------------------------- |
| `chapters` | `UNIQUE (book_id, number)`; `kind` enum `kb_chapterkind` (`chapter` / `front_matter` / `table_of_contents` / `appendix`) → `book`, `source_file` |
| `sections` | `UNIQUE (chapter_id, number)`; also → `book`, `source_file` |
| `subsections` | `UNIQUE (section_id, number)`; → `book`, `section`, `source_file` |
| `pages` | `UNIQUE (book_id, page_number)`; → `book`, `source_file`; `has_text` bool |
| `paragraphs` | `UNIQUE (book_id, page_id, sequence)`; keeps original pre-normalization text |
| `content_blocks` | typed element: `block_type` enum `kb_blocktype`, `sequence`, `original_text`, `status` enum `kb_contentstatus`, nullable `notes`; optional FKs → `page`/`chapter`/`section`/`subsection`; `UNIQUE (book_id, page_id, sequence)` |
| `content_chunks` | `chunk_id` `UNIQUE` (stable: `sha256(chapter:section:page:index)`), `UNIQUE (content_block_id, sequence)`; groups ≥1 paragraph (`metadata_["block_ids"]`); `language`, `token_count`, `page_start`/`page_end`, `chapter_id`/`section_id`, `text` (normalized variant where available), `is_normalized`, `metadata_` JSONB |

`chapters.kind` distinguishes real content from identified structural regions
so body text is never mistaken for them in search; `block_type` now also
includes `page_number`, `front_matter`, `toc_entry`, and `reference` beyond
the prose/heading/footnote/verse/hadith types.

`original_text` on blocks is guaranteed verbatim source text; the
*search/normalized* variant lives in `normalized_texts` and is what
`content_chunks.text` carries when a normalized variant exists (with
`is_normalized=true`), falling back to the original otherwise.

## Chunking pipeline

See `docs/chunking.md`. Migration `b62e5a8c1d7f_chunk_fields` adds the
provenance/token fields to `content_chunks` and drops the old
`UNIQUE (content_block_id, sequence)` in favour of multi-block chunks.

## Quran domain

| Table | Notable columns / constraints |
| ----- | ----------------------------- |
| `surahs` | natural key: `surah_number`-style via `number` `UNIQUE`; `name_arabic`, `name_romanized`, `name_en`, `ayah_count`, `revelation_type` |
| `ayahs` | `UNIQUE (surah_id, number)`; `text` (verbatim), `page_number`, `juz`, → `source_file` |
| `ayah_translations` | `UNIQUE (ayah_id, language, translator)`; `text` |

## Hadith domain

| Table | Notable columns / constraints |
| ----- | ----------------------------- |
| `hadith_collections` | `name` `UNIQUE` (e.g. `sahih-bukhari`), `title`, `author` |
| `hadith_books` | `UNIQUE (collection_id, name)` |
| `hadith_chapters` | `UNIQUE (collection_id, hadith_book_id, name)` |
| `hadiths` | `UNIQUE (collection_id, number)`; `text` verbatim, `grade`, `chain`, → `source_file`, optional → `hadith_book`/`hadith_chapter` |

## Search domain

`search_documents` — `UNIQUE (content_chunk_id, language)`; also supports
display-level rows (e.g. whole surah / hadith translation) via `document_type`.
`search_vector` is a `tsvector` with a GIN index
(`ix_search_documents_vector`); includes `title`, `body_text`, `language`.

## Embeddings domain

| Table | Notable columns |
| ----- | --------------- |
| `embedding_models` | `name` `UNIQUE`, `provider`, `dimensions`, `version` (`UNIQUE` per name), `metadata_` JSONB |
| `embeddings` | `UNIQUE (embedding_model_id, content_chunk_id)`; `vector` `vector(768)` with HNSW index `ix_embeddings_vector_hnsw` (cosine) |

The fixed 768-dimensional base column allows the HNSW index; a production
pipeline with a differently-dimensioned model can add a migration.

## Normalization domain

`normalized_texts` — one **search-normalized variant** per content block;
`UNIQUE (content_block_id)`. `original_text` is never written or updated here;
each row carries `original_sha256` (hash of the source `content_blocks.original_text`)
so the pairing is verifiable. `language` (`kb_language`), `config_name`
(`auto`/`conservative`/`search`/`urdu`), `normalized_text`, `protected`
(religious content marker present — variant kept byte-identical), `stats`
JSONB. `content_block_id` FK is `ON DELETE CASCADE`, so re-running structure
detection cleans stale variants automatically. `ProcessingJob(job_type=NORMALIZE)`
records each run.

## Provenance guarantee

Every leaf table (page, paragraph, block, chunk, ayah, hadith) carries
`source_file_id`; every intermediate object carries `book_id`/page/chapter
refs. Deleting a `source_files` row cascades to its editions, jobs, and
licenses; deleting a `books` row cascades to its chapters/pages/blocks/chunks
via ORM-level `cascade="all, delete-orphan"`, and a `content_block` delete
cascades to its `normalized_texts` row via DB-level `ON DELETE CASCADE`.

## Development commands

Reset + migrate the dev schema (container `islam24x7-db`, port 5434):

```pwsh
docker exec islam24x7-db psql -U knowledge_base -d knowledge_base -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; CREATE EXTENSION vector;"
$env:KB_DATABASE_URL="postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base"
.\.venv\Scripts\alembic.exe upgrade head
```

Round-trip both databases:

```pwsh
$env:KB_DATABASE_URL="postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test"
.\.venv\Scripts\alembic.exe downgrade base
.\.venv\Scripts\alembic.exe upgrade head
```

DB tests (`tests/test_database.py`) run against `knowledge_base_test` and are
skipped when the container is unreachable.