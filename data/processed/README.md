# processed/

Derived content produced by the pipeline — never manually edited, never
committed to git. Everything here can be regenerated from `data/raw/`.

## Subdirectories (created by pipeline stages)

| Directory    | Stage                                                     |
| ------------ | ---------------------------------------------------------- |
| `inspections/`   | PDF inspection reports (classification, page counts)       |
| `extracted/`     | page-by-page text extraction results                       |
| `ocr/`           | OCR results for scanned pages                              |
| `metadata/`      | book metadata (PDF metadata + filename + first pages)      |
| `structure/`     | detected chapter/section/paragraph structure               |
| `normalized/`    | normalization reports (JSON + Markdown)                    |

Content here is keyed by `source_file_id` (SHA-256 of the raw file) so results
repeatably map back to their source.

## Rules

- Regenerated, never hand-edited. If a report is wrong, fix the pipeline, not
  the file.
- Gitignored — do not commit, and do not rely on these files surviving across
  machines without running the pipeline.