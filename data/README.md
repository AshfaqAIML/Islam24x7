# data/

The `data/` tree is the single place where source material and derived
artifacts live. It is never a code directory: no `.py` files, no configuration,
no secrets.

## Layout

| Directory        | Purpose                                                            |
| ---------------- | ------------------------------------------------------------------ |
| `raw/`           | **Untouched source material** — the only read input of the pipeline |
| `processed/`     | Derived content produced by the pipeline (extracted text, OCR, normalizations, reports) |
| `exports/`       | Portable knowledge-base exports (JSON, Markdown dumps, DB snapshots) |
| `quarantine/`    | Files that failed validation or processing, moved here for review   |

## Rules

- `raw/` is **read-only by convention**: pipeline stages never modify files
  there. It is the ground truth everything else derives from.
- `processed/`, `exports/`, and `quarantine/` are **derived/sensitive** and are
  gitignored. Anything in them can be rebuilt or re-derived from `raw/`.
- Raw PDFs (`data/raw/**/*.pdf`) are gitignored because they are large binaries;
  the directory tree and these READMEs are tracked.
- Never place credentials, private keys, or personal data in this tree. Real
  configuration lives only in `.env` (gitignored).

## Source identity

Every file ingested into the pipeline is identified by the SHA-256 hash of its
raw bytes (see `src/knowledge_base/core/hashing.py`). That hash is the stable
`source_file_id` used across extraction, normalization, database, and exports.