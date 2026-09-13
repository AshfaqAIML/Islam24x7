# Structure detection pipeline

Detects the layout of a published book from its extract-stage page text and
materializes the **provenance spine**: front matter, table of contents,
chapters → sections → subsections, pages → paragraphs, and typed content
blocks. It is rule-driven and evidence-based: uncertain signals are *flagged
for review*, never guessed into structure.

## Input

`data/processed/extract/<sha256>/` — `pages/NNNN.txt` plus an `index.json`
that enumerates every physical page (blank pages included, marker `blank`).
When no `index.json` exists the detector falls back to the `pages/*.txt`
glob, so hand-made outputs and tests work too. A missing page file counts as
a blank page.

## Region & number model

Page layout is classified first, then segmented line by line:

| Region / signal | Handling |
| --------------- | -------- |
| Table of contents | leading-region page (`first 8 pages`) where ≥3 body lines look like TOC lines (≥3 leader dots **or** trailing 1–4-digit page ref) **and** ≥60% of body lines do; emitted as `TOC_ENTRY` blocks under chapter **-1** (`(table of contents)`) |
| Front matter | pages before the first confident chapter/appendix heading; paragraphs become `FRONT_MATTER` blocks under chapter **0** (`(front matter)`). If no real heading exists anywhere, no front matter is invented — the book stays plain paragraphs with `chapter_no = NULL` |
| Chapter / section / subsection | `HEADING` blocks (validated) + structural rows, numbered 1..N (sections reset per chapter, subsections per section) |
| Page-number lines | dropped entirely and counted (`dropped_page_numbers`) |
| Running header repeats | a heading whose normalized title equals the currently-open chapter/section/subsection *opened on an earlier page* is suppressed and counted (`suppressed_repeats`) |
| Footnotes | marker/star/long-separator lines → `FOOTNOTE` blocks |
| References / appendices | marker-based chapters (`References`, `المراجع`, ...) emit `REFERENCE` blocks (no paragraph rows); `الملحق`/`appendix`/... chapters become `kind = appendix` |

References chapters get `kind = chapter` but their blocks are `REFERENCE`
type, so bibliography entries are never indexed as body prose. Only
`PARAGRAPH` blocks produce `Paragraph` rows, and only inside normal chapters.

## Heading evidence (confidence)

A line is a **confident** heading when it starts with a recognized marker
(`chapter_markers` / `section_markers` / `subsection_markers` /
`appendix_markers` / `references_markers`) followed by a non-word boundary
(never a partial word like `فصلان`), or matches dot-separated numbering
(`1.2` → section, `1.2.3` → subsection). Arabic ordinals (`الأولى`, ...
`العشرون` and `حادي عشر`-style compounds) and Arabic-Indic/Urdu digits are
parsed; markers are matched against a normalized form that strips harakat,
tatweel, and maps variant letters (`أإآ`.`→ا`, `ة→ه`, `ى→ي`, `ک→ك`, `ھ/ہ→ه`).

**Uncertain** (review) signals:
- isolated short lines (2–14 words, ≤ 90 chars, no sentence-ending punct,
  surrounded by blank lines) that match no marker → `HEADING` block with
  `status = review`, no structural row.

Nothing else creates structure. Browsing a bad or OCR-garbled extraction
therefore yields zero chapters and a large `flagged` count instead of
fabricated headings.

## Rules of thumb

- **Evidence wins.** Markers + numbering = structure; looks-like = review.
- **Idempotent.** Re-running the detector rewrites the book's rows
  (chapters → sections → subsections → pages → paragraphs → blocks) in place.
- **Page-true.** Page rows mirror the physical extract index, including
  blank pages (`has_text` = false).

## CLI

```
knowledge-base structure detect --all                    # every published book
knowledge-base structure detect --sha256 <prefix>
knowledge-base structure show    --sha256 <prefix>       # chapters + flagged review list
knowledge-base structure review  --sha256 <prefix> --list      # pending review rows
knowledge-base structure review  --sha256 <prefix> --approve <page>:<seq> [--note ...] [--reviewer ...]
knowledge-base structure review  --sha256 <prefix> --reject <page>:<seq> --note "why"
```

`approve` → `published`, `reject` → `quarantined`; the reviewer/note audit
fields are appended to the block's `notes`. Reports land in
`data/processed/structure/<sha256>.{json,txt}`, and each run upserts a
`ProcessingJob(STRUCTURE)` manifest summarizing counts.

## Tests

`tests/test_structure.py` covers English and Arabic books (markers, ordinals,
dotted numbering, appendices, references, footnotes, page-number drops,
running-header suppression, uncertain-flagging), plain books with no
structure markers, blank pages via `index.json`, unit helpers, and
idempotent re-runs. Run against the test database:

```pwsh
$env:KB_TEST_DATABASE_URL="postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test"
uv run pytest -q
```