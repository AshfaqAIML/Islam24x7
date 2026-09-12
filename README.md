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

This repository is being built incrementally. The first milestone
(**normalization pipeline**) is implemented and tested; the full architecture
and the remaining milestones are documented in
[`docs/architecture.md`](docs/architecture.md).

## Requirements

- Python 3.12+

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

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
src/knowledge_base/
├── __init__.py
└── normalization/           # implemented
    ├── models.py            # NormalizationConfig / Result / Report
    ├── normalize.py         # normalize_text()
    └── report.py            # JSON + Markdown reports
docs/
└── architecture.md          # full architecture + milestones
tests/
└── test_normalization.py    # proves original text is never altered
```

## Security

- Credentials live only in local `.env` (gitignored); `.env.example` holds
  placeholders.
- Derived data (`data/processed/`, `data/exports/`, `data/quarantine/`) is
  gitignored.
- No private keys or secrets are ever committed.