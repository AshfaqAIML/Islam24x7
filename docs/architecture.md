# Islamic Knowledge Base — Architecture

**Status:** Implemented. The complete pipeline below is built, tested (326 tests),
type-checked (mypy strict), and linted (ruff). The repository already contains the
CLI orchestrator, the PostgreSQL + pgvector schema, the search/RAG stack, the
FastAPI backend, and the verified Quran/hadith dataset seeder.

## 0. System overview

```
                     YOUR PDF COLLECTION
                            │
                            ▼
                   ┌─────────────────┐
                   │ PDF INSPECTOR   │
                   └────────┬────────┘
                            ▼
                 ┌─────────────────────┐
                 │ TEXT / OCR ENGINE   │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ METADATA EXTRACTION │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ STRUCTURE DETECTOR  │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ NORMALIZATION       │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │ STRUCTURED CONTENT  │
                 └──────────┬──────────┘
                            ▼
                 ┌─────────────────────┐
                 │     CHUNKING        │
                 └─────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │     POSTGRESQL         │
              │                        │
              │ Books                  │
              │ Chapters               │
              │ Pages                  │
              │ Content                │
              │ Quran                  │
              │ Hadith                 │
              └───────────┬────────────┘
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
      FULL TEXT SEARCH            EMBEDDINGS
             │                         │
             │                         ▼
             │                    PGVECTOR
             │                         │
             └────────────┬────────────┘
                          ▼
                   HYBRID SEARCH
                          │
                          ▼
                       RAG
                          │
                          ▼
                    AI RESPONSE
                          │
                          ▼
                VERIFIED CITATIONS
                          │
                          ▼
                 EXACT BOOK PAGE
```

Every box in the diagram maps to a module in `src/knowledge_base/` (see §5) and
is exercised end-to-end by the `kb` CLI. Quran and Hadith enter the database
through the validated dataset seeder (`kb seed-quran` / `kb seed-hadith`), books
through the PDF ingestion pipeline.

## 1. Scope and objective

Build a **local, Python-based, processing-first** knowledge system that ingests:

- Quran datasets
- Hadith datasets
- Islamic books (fiqh, tafsir, aqeedah, seerah, history, other)
- Other authorized Islamic publications

Sources are primarily **PDF**, with the pipeline extensible to **EPUB, DOCX,
TXT, Markdown, HTML, structured JSON**.

The output is a *validated, traceable Knowledge Base* consumed later by a
web/mobile application and an AI/RAG system. **The KB system itself is built
now; the application and RAG are future consumers.**

## 2. Critical principles (non-negotiable)

1. Never modify original source files.
2. Preserve source provenance on every artifact.
3. Never invent Islamic content.
4. Never use an LLM to reconstruct Quran or Hadith text.
5. Preserve page references.
6. Preserve chapter/section hierarchy.
7. Every processed passage traces back to its source.
8. Every chunk has a stable identifier.
9. Arabic, Urdu, English, and multilingual content.
10. Scales to thousands of books.
11. Processing is incremental and resumable.
12. Failed documents never corrupt the database (transactional + quarantine).
13. Human review is possible before publication.
14. AI/RAG operates only on verified, indexed source material.

These principles drive every architectural decision below.

## 3. Pipeline overview

```
Source Files
   → 1. Ingestion (register, hash, quarantine, license check)
   → 2. Inspection (pages, text layer, scanned/mixed, corruption, language)
   → 3. Text Extraction (page-by-page, reading order, Unicode)
   → 4. OCR (only scanned pages; AR/UR/EN; never fabricate)
   → 5. Metadata (title/author/year/ISBN/... + human review)
   → 6. Document Structure (chapters/sections/pages/blocks; review flags)
   → 7. Normalization (original + search variant; never touch source)
   → 8. Chunking (stable chunk IDs, page-anchored)
   → 9. Full-Text Index (PostgreSQL + tsvector + multilingual config)
  → 10. Embeddings (pgvector; model metadata recorded)
  → 11. Vector Index (HNSW/IVFFlat)
→ 12. Validation (cross-checks, provenance audit, quarantine)
   → 13. Knowledge Base (verified + review/publish workflow)
   → 14. Seeding (verified Quran/hadith datasets) and
         Search / RAG / API consumers
```

Quran and Hadith bypass the PDF pipeline and enter the same schema through the
validated dataset seeder (§14), which is idempotent, refuses to overwrite
existing sacred text, and records `source_file_id` provenance on every row.

Every stage is **idempotent and resumable**: it consumes recorded inputs, writes
a manifest, and can be re-run safely. Stages write only to the database; raw
sources are read-only.

## 4. Technology stack

| Area            | Choice                                    | Rationale |
| --------------- | ----------------------------------------- | --------- |
| Language        | Python 3.12+                              | team consistency, ecosystem |
| Packaging       | `pyproject.toml`, src-layout, venv        | modern, reproducible |
| Config          | `pydantic-settings` + `.env`              | typed, env-driven |
| Logging         | `loguru` structured logging               | low-friction structured logs |
| PDF read/inspect| PyMuPDF (`fitz`)                          | fast, per-span font/bbox, outline, render to image |
| Render for OCR  | PyMuPDF pixmaps + Pillow                  | accurate page rasterization |
| OCR             | EasyOCR primary (AR/UR/EN), Tesseract alt | full language support; documented setup |
| Models          | Pydantic v2                               | validation, serialization, JSON manifests |
| Database        | PostgreSQL 18 + pgvector                  | single source of truth; FTS + vectors in one place |
| Migrations      | Alembic                                   | versioned schema |
| Full-text       | PostgreSQL `tsvector` + GIN               | AR/UR configs, no extra service |
| Embeddings      | pgvector (`vector` + HNSW)                | duplicate-free, SQL-integrated |
| Lint/format     | ruff                                      | speed, single tool |
| Types           | mypy (strict)                             | correctness |
| Tests           | pytest                                    | fixture factories, tmp_path PDFs |

Deliberately absent: No message broker, no microservices, no cloud dependency.
A simple SQL state table drives the incremental pipeline.

## 5. Folder structure

```
Islam24x7/
├── pyproject.toml
├── .env.example
├── docs/                       # cli.md, architecture.md, ...
├── src/knowledge_base/
│   ├── config.py               # pydantic-settings
│   ├── logging.py              # structured logging setup
│   ├── pipeline/               # ingestion stages, each idempotent/resumable
│   │   ├── ingest/             # registration, hashing, quarantine
│   │   ├── inspect/            # PDF inspection + classification
│   │   ├── extract/            # page-by-page text extraction
│   │   ├── ocr/                # OCR engines, quality
│   │   ├── metadata/           # book metadata extraction + review
│   │   ├── structure/          # chapter/section/page/block detection
│   │   ├── normalize/          # safe multilingual normalization
│   │   ├── chunk/              # stable-ID chunking
│   │   ├── index/              # FTS (tsvector) indexing
│   │   ├── embed/              # embedding generation
│   │   ├── validate/           # validation + provenance audit
│   │   └── seed/               # verified Quran/hadith dataset seeding
│   ├── search/                 # hybrid (FTS + pgvector) query engine
│   ├── rag/                    # retrieval + grounded generation + citations
│   ├── api/                    # FastAPI backend (kb serve)
│   ├── database/               # SQLAlchemy models, Alembic migrations
│   └── cli/                    # `kb` orchestrating CLI
└── tests/
```

Raw PDFs live under the repository-adjacent `Books/` directory (read-only by
convention); every derived artifact keeps its `source_file_id` provenance.

## 6. Database architecture (PostgreSQL + pgvector)

Tables grouped by domain (full schema documented with migrations):

**Sources**
- `source_files` — path, sha256, format, mime, size, status; *files never stored
  as blobs* — only path + hash (large PDFs live on disk)
- `source_editions` — edition title, publisher, year, ISBN, language
- `licenses` — for the source file distribution rights
- `processing_jobs` — kind, status, started/finished, error, manifest jsonb

**Books catalog**
- `books`, `authors`, `translators`, `editors`, `publishers`
- `categories`, `topics` (with the approved taxonomy: fiqh, tafsir, aqeedah,
  seerah, history, hadith, quran, other)

**Book structure**
- `chapters`, `sections`, `subsections`, `pages`, `paragraphs`, `content_blocks`
  — each keeps `source_file_id`, `page_number`, `parent_id`, `sequence`,
  `original_text`

**Quran** — `surahs`, `ayahs`, `translations`
**Hadith** — `collections`, `hadith_books`, `hadith_chapters`, `hadiths`

**Search & vectors**
- `search_documents` — text + `tsvector` + GIN index, doc type, language
- `embedding_models` — name, provider, dims, version
- `embeddings` — `vector(dims)` (pgvector), chunk_id, model_id; HNSW index

**Provenance & review**
- Every content row carries `source_file_id`, `page_number`, `parent_id`,
  `sequence`, `processing_job_id`
- `review_flags` — element + reason + status (pending/reviewed/rejected)
- Content status enum: `pending → validated → review → published → quarantined`

**Stable IDs:** UUID primary keys (generated once, never reused); natural unique
keys where they exist (surah no., ayah no., hadith no., collection names).
Chunk IDs embed source hash + page + sequence to stay stable across re-runs.

## 7. Ingestion pipeline design

1. **Register**: compute SHA-256; insert `source_files` row (status =
   `registered`) — transactional.
2. **Inspect** → classification (`TEXT_PDF`, `SCANNED_PDF`, `MIXED_PDF`,
   `INVALID_PDF`), page count, corruption/encryption flags.
3. **Extract** pages (text layer), per page: source_id, page_number, text,
   method, status, confidence. Empty/poor pages flagged.
4. **OCR** only pages that require it; results stored separately from source
   images; quality report; `REVIEW` for low confidence.
5. **Metadata**: PDF metadata → filename → title page → user input; merged with
   per-field confidence; human-review workflow before any "verified" flag.
6. **Structure**: outline + font-size + pattern signals → hierarchy tree with
   review flags on uncertainty.
7. **Normalize**: original retained; search variant produced; religious content
   protected from folding.
8. **Chunk**: stateful (hash-based) chunking with stable IDs.
9. **Index + Embed**: FTS insert and vector insert in the same transaction.
10. **Validate**: provenance audit (every chunk resolves to a source row), page
    range checks, redundancy/no-orphan checks; failures go to quarantine.

**Seed entry point:** `kb seed-quran`/`kb seed-hadith` validate a curated JSON
dataset (pydantic), register its `SourceFile` by SHA-256, and insert
surahs/ayahs/translations and collections/hadiths by natural key. Rows already
present are skipped; conflicting sacred text aborts the run transactionally
(`SeedConflictError`).

**Failure isolation:** any step failure marks the job `failed`, rolls back that
unit's DB writes, and leaves the source quarantinable — never a corrupt state.

## 8. Search architecture

- **Retrieval**: PostgreSQL full-text (`tsvector`) with language-aware configs
  — `arabic`, `urdu` (arabic-based), `english`; GIN index. Quran and hadith
  rows get their tsvectors from the same domain triggers.
- **Hybrid**: FTS candidates ∪ vector-similarity candidates, fused by rank;
  results are resolved back to `content_chunks` → pages → source/citation.
- **Multilingual**: per-document language from metadata/script detection;
  `simple` config fallback for mixed documents.
- **Scope**: query planner restricts to published/verified content by default.

## 9. Embedding architecture

- `embedding_models` tracked (provider, dims, version) — embeddings are tagged
  so model upgrades do not silently mix vectors per chunk (`UNIQUE(model_id,
  chunk_id)`).
- `pgvector` `vector(n)` column + HNSW index for ANN search.
- Generation is a pipeline job writing chunk text (from the *normalized* but
  **never** the source-replacing variant) — original wording is untouched.
- Embeddings for religious text use the same protection rules as normalization
  (no data invention; deterministic, non-LLM).

## 10. Validation architecture

Three layers:
1. **Structural validators** — page overlaps, empty-page thresholds, ordering,
   structure→page referential integrity.
2. **Content validators** — duplicate detection, garbled-text heuristics,
   language-script consistency, Quran/hadith cross-checks against
   authenticated sources (never LLM reconstruction).
3. **Provenance audit** — for every chunk, walk source chain; report orphaned
   or broken rows. Fail → quarantine.

A **review queue** (`review_flags`) lets a human inspect flagged items; nothing
reaches the published KB without passing validation (+ review where flagged).

## 11. Citation / provenance architecture

A strict foreign-key chain per passage:

```
content_chunk → content_block → page/paragraph
              → source_page → source_file → source_edition → license
```

Each hop stores `source_file_id`, `page_number`, `parent_id`, `sequence`. The
RAG retrieval layer renders verified citations `(author, title, edition, p. N,
chunk id)` from this chain and is **citation-constrained**: generated answers
may only quote chunks resolved through this chain. Responses that cannot be
grounded are returned with `grounded=False` rather than fabricated.

## 12. Scaling from 5 books to thousands

| Lever | Mechanism |
| ----- | --------- |
| Incremental | Per-file pipeline state; only new/changed files processed |
| Idempotency | Stable IDs + manifests; re-runs are safe no-ops |
| Batch, not stream | process book-by-book; checkpoint DB each step |
| Cost control | OCR only on scanned pages; embeddings batched; pgvector ANN |
| Reproducibility | recorded engine versions, config, and hashes in manifests |
| Review triage | priority queue; only flagged passages need humans |
| Storage | PDFs on disk; only text/vectors in DB |
| Isolation | per-job transactions; quarantine isolates bad sources |
| Parallelism | independent books processed concurrently later (same code) |
| Archival | exports/ + quarantine/ keep the DB small and trustworthy |

## 13. Milestones

**M0 — Foundation** (packaging, config, logging, venv, tooling) — done
**M1 — Ingestion + Inspection** (register/hash/quarantine; PDF inspection +
classification) — done
**M2 — Extraction + OCR** (text layer extraction; OCR with review flags) — done
**M3 — Metadata normalization + review** — done
**M4 — Structure detection + chunking** (hierarchy detection; stable-ID
chunking) — done
**M5 — Database schema + migrations** (SQLAlchemy + Alembic, PostgreSQL +
pgvector; 10 migrations) — done
**M6 — FTS + Embeddings + Vector index** (search_documents tsvector, pgvector
HNSW) — done
**M7 — Validation + Provenance audit** — done
**M8 — Verified dataset seeding** (Quran + Hadith, idempotent, conservative)
— done
**M9 — CLI + Query/RAG + API** (`kb` CLI, hybrid search, RAG with verified
citations, FastAPI `kb serve`) — done

Each milestone ships with tests, lint/type checks, and a documented demo.

## 14. What has been built

| Area | Location | Status |
| ---- | -------- | ------ |
| PDF ingestion/inspection | `pipeline/ingest`, `pipeline/inspect` | done |
| Text extraction + OCR | `pipeline/extract`, `pipeline/ocr` | done |
| Metadata + structure | `pipeline/metadata`, `pipeline/structure` | done |
| Normalization | `pipeline/normalize`, `normalization/` | done |
| Chunking (stable IDs) | `pipeline/chunk` | done |
| DB schema + 10 migrations | `database/` (+pgvector) | done |
| FTS index | `pipeline/index` (tsvector, AR/UR/EN configs) | done |
| Embeddings | `pipeline/embed` (pgvector HNSW) | done |
| Validation/provenance | `pipeline/validate` | done |
| Quran/Hadith seeding | `pipeline/seed` + `kb seed-quran`/`seed-hadith` | done |
| Hybrid search | `search/engine.py` (FTS ∪ pgvector) | done |
| RAG + citations | `rag/` (retrieval, generation, service) + `kb ask` | done |
| HTTP API | `api/` + `kb serve` | done |
| CLI | `cli/kb` (ingest, extract, ocr, structure, normalize, chunk, index, embed, validate, reindex, search, ask, serve, stats, status, export, inspect, process, seed) | done |

Test inventory: 326 tests — pipeline stages, database, search, RAG, API,
CLI, and seeding all covered.