# Islam24x7 Knowledge Base

A local, Python-based Islamic Knowledge Base processing system. It ingests
Quran datasets, hadith collections, and Islamic books (PDF-first, extensible to
EPUB/DOCX/TXT/HTML/JSON), converts them into a validated, traceable knowledge
base, and exposes it through full-text + semantic search, source-grounded
question answering (RAG), and a JSON HTTP API.

> **Source fidelity is the top priority.** Original source files are never
> modified. Every processed passage keeps a chain of provenance back to its
> source file and page. No Islamic content is ever invented or silently
> corrected.

## Status

All five workstreams are implemented and tested:

| Workstream | Deliverable | Tests |
| ---------- | ----------- | ----- |
| W1 CLI | `kb` command-line operator (11 commands) | 15+ |
| W2 Coverage | 24 test modules across the pipeline, search, database | 315 total |
| W3 RAG | Source-grounded retrieval + extractive generation (`kb ask`) | 21 |
| W4 API | FastAPI backend (`kb serve`) | 9 |
| W5 Audit | Production hardening + docs (this file) | — |

Gates: `pytest` (315 passing), `ruff check .`, `mypy src` — all clean.

## Requirements

- Python 3.12+
- PostgreSQL 16 with the `vector` extension (dev/test container on port 5434)

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and adjust the database URL, or set `KB_*`
environment variables.

## Configuration

`pydantic-settings` resolves values in increasing priority: defaults, local
`.env`, `KB_*` environment variables. Key settings:

| variable                  | default   | description                       |
| ------------------------- | --------- | --------------------------------- |
| `KB_DATA_DIR`             | `./data`  | root of the data tree             |
| `KB_DATABASE_URL`         | —         | PostgreSQL URL (dev/test)         |
| `KB_TEST_DATABASE_URL`    | —         | PostgreSQL test URL               |
| `KB_LOG_LEVEL`            | `INFO`    | log level                         |
| `KB_EMBEDDING_PROVIDER`   | `dummy`   | embedding provider               |
| `KB_EMBEDDING_MODEL`      | `kb-dummy`| embedding model name              |
| `KB_EMBEDDING_DIMENSIONS` | `768`     | vector dimensions                 |

The embedding provider is pluggable: `dummy` for local/dev
(`DummyEmbeddingProvider`, deterministic) or a `pkg.module:ClassName` path for
real embeddings. When an embedding provider is unavailable at run time,
retrieval degrades automatically to keyword-only search.

## Command-line interface

The primary CLI is `kb`:

```
kb import  <path>...            register raw files/directories
kb inspect <file.pdf>           classify a file (text / scanned / mixed)
kb process [--sha256 …]         run the processing pipeline
kb validate [--sha256 …]        integrity + provenance audit
kb search  "<query>"            full-text search (Quran, hadith, books)
kb ask     "<question>"         source-grounded RAG answer
kb embed [--all]                generate chunk embeddings
kb reindex [--all]              rebuild full-text search documents
kb status                       knowledge-base dashboard
kb retry                        re-run failed/pending stages
kb stats                        aggregate statistics
kb export [--all]               export books to JSON
kb serve [--port 8000]          run the HTTP API
```

`kb ask` retrieves passages with hybrid keyword + semantic search, generates an
extractive answer that cites its sources (`[S1] … [Sn]`), and reports a
`GROUNDED`/`UNGROUNDED` verdict from `verify_grounding` plus the citations.
Every citation is rebuilt from the stored chunk row — never invented.

Full command documentation lives in [`docs/cli.md`](docs/cli.md).

### HTTP API

`kb serve` exposes JSON endpoints:

- `GET  /health` — liveness
- `GET  /status` — dashboard counts
- `POST /ask`    — RAG answer `{"question": "…", "k": 5}`
- `POST /search` — full-text search `{"query": "…", "limit": 10}`

## Pipeline

Each book flows through: ingestion (hash + quarantine) → inspection →
extraction → OCR (pluggable) → metadata review → structure detection →
chunking (stable, structure-aware IDs) → full-text indexing → embeddings →
validation. Every stage writes a `ProcessingJob` so work is resumable
(`kb process --pending`, `kb retry`).

Normalization interns two versions of every text: `original` (verbatim,
never modified) and `normalized` (a separate search-oriented variant). Both
profiles skip character-level folding when the text contains protected
religious markers (Quranic ornaments, basmala, ﷺ/ﷻ, common hadith phrases).

## Verification commands

```powershell
pytest                       # 315 tests (pipeline, search, RAG, API, CLI)
ruff check .                 # lint
ruff format --check .        # formatting
mypy src                     # strict type checking
```

Run the suite against the test database:

```powershell
$env:KB_DATABASE_URL="postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test"
pytest
```

## Project layout

```
Islam24x7/
├── data/                      # raw (tracked), processed/, exports/, quarantine/
├── docs/
│   ├── architecture.md        # architecture + milestones
│   └── cli.md                 # kb command reference
├── src/knowledge_base/
│   ├── api/                   # FastAPI application (ask/search/status)
│   ├── cli/kb/                # kb CLI parser + command implementations
│   ├── config.py              # pydantic-settings configuration (KB_* env)
│   ├── core/                  # hashing, logging, helpers
│   ├── database/              # SQLAlchemy models, session helpers, enums
│   ├── normalization/         # original/normalized text pair handling
│   ├── pipeline/              # ingest, inspect, extract, ocr, metadata,
│   │                          # structure, chunk, index, embed, validate
│   ├── rag/                   # retrieval, generation, grounding, service
│   └── search/                # query API, hybrid retrieval, vector search
└── tests/                     # 24 modules, 315 tests
```

## Security

- Credentials live only in local `.env` (gitignored); `.env.example` holds
  dev-only placeholders.
- Derived data (`data/processed/`, `data/exports/`, `data/quarantine/`) is
  gitignored.
- No private keys or production secrets are committed.
