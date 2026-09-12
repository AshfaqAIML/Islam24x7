# raw/hadith/

Authentic hadith collections — never modified. A file here is one collection
or a portion of one:

- e.g. `sahih-bukhari.json`, `sahih-muslim.json`, `sunan-abu-dawud.txt`

## Conventions

- A single collection per file.
- Use standard hadith identifiers where available: collection name + hadith
  number (e.g. Bukhari 1) and chapter/section.
- Meta-data (narrator, book, chapter, grade) travels with the text; the
  pipeline records it in `hadiths` / `hadith_chapters`.

## Rules

- Unmodified source of truth; the pipeline never edits it.
- Derived hadith records/embeddings are produced in `data/processed/`.