# raw/

Raw **source material**, untouched. This is the only input of the pipeline.

## Contents

- `quran/`   — Quran datasets (e.g. authenticated mushaf text, translations)
- `hadith/`  — Hadith collections (e.g. Sahih al-Bukhari, Sahih Muslim, ...)
- `books/`   — Islamic books, organised by category (see `books/README.md`)

## Rules

- **Never modify** anything in this tree. Files here are the ground truth.
- **Never derive in place** — processed output goes to `data/processed/`.
- **Never commit large binaries**: raw PDFs are gitignored
  (`data/raw/**/*.pdf`). Small reference files (TXT, JSON manifests, scripts
  that generate datasets) may be committed.
- Only add material you hold a right to process. License tracking is handled by
  the ingestion pipeline (`source_editions` / `licenses`).

## Adding a file

1. Place the file in the appropriate category directory.
2. The ingestion pipeline registers it by SHA-256, inspects it, and quarantines
   it on failure — `raw/` keeps a pristine copy throughout.

## Source identity

`source_file_id` = SHA-256 of the raw file bytes. Renaming or moving a file
never changes its identity; changing its content does.