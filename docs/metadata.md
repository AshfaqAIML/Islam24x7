# Metadata extraction pipeline

Local-extraction stage that derives **evidence-backed, reviewable metadata**
for every registered source file. Nothing is invented: if a signal is
ambiguous the field is flagged `uncertain` and left for a human; only an
explicit `approve` + `publish` moves metadata into the verified catalog
(`books` / `source_editions`).

## Sources & fields

| Source | Fields produced | Confidence |
| ------ | --------------- | ---------- |
| PDF info dict (`pdf_metadata`) | `title`, `author` (high); `description` from `subject` (medium) | high |
| Filename slug (`filename`) | `title` guess (low, uncertain); `edition` from `vol 2` / `juz 1` patterns (medium) | low |
| First pages scan (`title_page` / `first_pages`) | marker-based `author` (`تأليف`/`by`), `editor` (`تحقيق`), `translator` (`ترجمة`), `publisher` (`دار`…), `edition` (`الطبعة…`); Hijri years (`هـ`/`ھ`, incl. Arabic-Indic digits) as `NNNN (AH)`; ISBN-13; probable title line; language via script detection | high / medium |
| Operator input (`user_provided`) | any field via `--user-json` or `metadata review --value` | high |

Fields supported: `title`, `subtitle`, `author`, `translator`, `editor`,
`publisher`, `publication_year`, `edition`, `language`, `isbn`, `category`,
`description`, `page_count`.

**Uncertainty rules** — never auto-published until approved:
- filename title guesses    → `low` / `uncertain`
- bare 4-digit year         → `medium` / `uncertain`
- a non-basmala long line   → `medium` / `uncertain` (best-effort title)
- `user_provided` rows are written `approved` (`reviewed_by = operator`)
  but still need the `publish` step.

Overall confidence = weakest link among found fields (any `low` → `low`).

## Flow

```
knowledge-base metadata extract  --all [--limit N] [--user-json meta.json]
knowledge-base metadata show     --sha256 <prefix>
knowledge-base metadata review   --sha256 <prefix>
knowledge-base metadata review   --sha256 <prefix> --approve title --reviewer name
knowledge-base metadata review   --sha256 <prefix> --reject author --note "wrong"
knowledge-base metadata review   --sha256 <prefix> --approve title --value "Corrected" \
                                 --reviewer name [--publish]
```

- `extract` persists one candidate row per `(field, source, value)`; re-runs
  dedupe on that key so approvals/rejections survive, and stale candidates
  (including stale user input) are removed.
- Reports land in `data/processed/metadata/<sha256>.{json,txt}`; the
  `ProcessingJob(METADATA)` manifest tracks fields, confidence counts, and
  `uncertain_fields`.
- `review` acts on the *best* candidate for a field (approvals outrank
  confidence; rejected candidates are retired).
- `publish` materializes approved candidates into a `book` +
  `source_edition`, get-or-creating `author` / `translator` / `publisher` /
  `category` by name. Requiring an approved `title` guards against junk rows.

## Example

`data/raw/…/tadhkirah-ibn-mulaqqin.pdf` → title/author `high` from PDF info,
`publication_year 1436 [uncertain]` from a printed column heading, language
`ar` from page script. After `approve title+author+language` +
`--publish`, a verified `book` links back to the raw file via
`books.source_file_id` (provenance chain intact).

## Design notes

- Stay pure & import-light: extractors are pure functions; the only new
  runtime dep is `pymupdf` (already used by inspect/extract).
- No OCR needed here; if the text layer is absent on the title pages the scan
  yields no candidates — the human is the fallback.
- Large-scale cleanup: reject + republish in place; there is no batch override
  yet (add before the structure milestone if the library grows fast).