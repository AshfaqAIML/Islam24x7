# Islam24x7 Knowledge Base

A local, Python-based Islamic Knowledge Base processing system. It ingests
Quran datasets, hadith collections, and Islamic books (PDF-first, extensible to
EPUB/DOCX/TXT/HTML/JSON), and converts them into a validated, traceable
knowledge base for later use by a web/mobile application and AI/RAG systems.

> **Source fidelity is the top priority.** Original source files are never
> modified. Every processed passage keeps a chain of provenance back to its
> source file and page. No Islamic content is ever invented or silently
> corrected.

## Status

This repository is being built incrementally. The **project foundation**
(packaging, environment, config, logging, CLI) and the **normalization
pipeline** are implemented and tested; the full architecture and the remaining
milestones are documented in [`docs/architecture.md`](docs/architecture.md).

## Requirements

- Python 3.12+

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

This installs the `knowledge-base` console script and all runtime + dev
dependencies.

## Configuration

Configuration is managed with `pydantic-settings`. Copy `.env.example` to
`.env` and adjust values; environment variables override the dotenv file.

| variable              | default | description                    |
| --------------------- | ------- | ------------------------------ |
| `KB_DATA_DIR`         | `./data`| root of the data tree          |
| `KB_LOG_LEVEL`        | `INFO`  | log level                      |
| `KB_DATABASE_URL`     | —       | PostgreSQL URL (future)        |
| `KB_TEST_DATABASE_URL`| —       | PostgreSQL test URL (future)   |

`Settings` is environment-driven (`KB_` prefix) and available package-wide via
`get_settings()`.

## Logging

Structured logging is provided through `loguru`, configured once at entry
points:

```python
from knowledge_base.logging import configure_logging

configure_logging("INFO")   # default: colorized, key=value records on stderr
```

## Command-line interface

```powershell
knowledge-base --version          # installed version
knowledge-base env                # resolved configuration
knowledge-base env --as-json      # configuration as JSON
knowledge-base glob "**/*.pdf"    # list files under KB_DATA_DIR
knowledge-base normalize docs/sample.txt
```

`python -m knowledge_base` is equivalent to `knowledge-base`. `env` prints the
runtime configuration; `normalize` runs the normalization pipeline on a
plain-text file and writes a report under `data/processed/normalized/`.

## Using the normalization pipeline

```python
from knowledge_base.normalization import normalize_text, search_config

result = normalize_text(
    "أحمد إبراهيم آدم المؤمنة",
    search_config(),
)
assert result.original == "أحمد إبراهيم آدم المؤمنة"  # always preserved
# result.normalized -> "احمد ابراهيم ادم المومنة"
```

Two configuration profiles are provided:

- `conservative_config()` — layout-only: Unicode NFC, whitespace and line-break
  cleanup, tatweel removal. Letter-level folding is never applied. Safe for all
  content.
- `search_config()` — additionally folds Arabic hamza/teh-marbuta/alef-maksura
  forms and Arabic-Indic digits for search indexing.

Both profiles **skip all character-level folding** whenever the text contains a
protected religious marker (Quranic ornaments, basmala, ﷺ/ﷻ, common hadith
phrases) so that Quran and hadith wording is never altered.

### Core invariant

`NormalizationResult` always carries two versions:

| field       | content                                                        |
| ----------- | -------------------------------------------------------------- |
| `original`  | the verbatim source string — never modified                    |
| `normalized`| a separate, search-oriented variant used only for indexing     |

`original` is stored unchanged and is never overwritten by `normalized`.

## Verification commands

```powershell
pytest                       # tests (currently: normalization)
ruff check src tests         # lint
ruff format --check src tests
mypy src                     # type checking
```

## Project layout

```
Islam24x7/
├── data/
│   ├── raw/                      # untouched source material
│   │   ├── quran/                # mushaf text, translations
│   │   ├── hadith/               # hadith collections
│   │   └── books/                # fiqh/ tafsir/ aqeedah/ seerah/ history/ other/
│   ├── processed/                # derived content (extracted, ocr, normalized, ...)
│   ├── exports/                  # portable knowledge-base exports
│   └── quarantine/               # failed validation/processing
├── docs/
│   └── architecture.md           # full architecture + milestones
├── src/knowledge_base/
│   ├── __init__.py
│   ├── config.py                 # pydantic-settings configuration (KB_* env)
│   ├── logging.py                # loguru structured logging
│   ├── __main__.py               # python -m knowledge_base entry
│   ├── core/
│   │   └── hashing.py            # SHA-256 source/content hashing
│   ├── cli/
│   │   ├── __init__.py           # argparse CLI (knowledge-base script)
│   │   └── commands.py           # command implementations
│   ├── pipeline/                 # ingestion pipeline stages
│   │   ├── ingest/               # registration, hashing, quarantine
│   │   ├── inspect/              # PDF inspection + classification
│   │   ├── extract/              # page-by-page text extraction
│   │   ├── ocr/                  # OCR for scanned pages
│   │   ├── metadata/             # book metadata + review
│   │   ├── structure/            # chapter/section/block detection
│   │   ├── chunk/                # stable-ID chunking
│   │   ├── index/                # full-text indexing
│   │   ├── embed/                # embedding generation
│   │   └── validate/             # validation + provenance audit
│   ├── normalization/            # implemented
│   │   ├── models.py             # NormalizationConfig / Result / Report
│   │   ├── normalize.py          # normalize_text()
│   │   └── report.py             # JSON + Markdown reports
│   ├── database/                 # SQLAlchemy models, Alembic migrations
│   └── search/                   # query API
└── tests/
    ├── conftest.py
    ├── test_config.py            # config + CLI tests
    └── test_normalization.py     # proves original text is never altered
```

The raw data directories (`data/raw/**`) are tracked; derived data
(`processed/`, `exports/`, `quarantine/`) is gitignored.

## Security

- Credentials live only in local `.env` (gitignored); `.env.example` holds
  placeholders.
- Derived data (`data/processed/`, `data/exports/`, `data/quarantine/`) is
  gitignored.
- No private keys or secrets are ever committed.