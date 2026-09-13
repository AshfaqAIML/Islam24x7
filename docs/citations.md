# Source provenance & citations

Every search hit, embedding, and content chunk can be traced back to the
database record (and the original source file) it came from. Citations are a
stable, JSON-serialisable contract built **exclusively** from loaded ORM rows
and their relationships — nothing is guessed or extrapolated.

## The `Citation` contract

`Citation` is a frozen dataclass produced by the builders in
`src/knowledge_base/citations.py`. It carries one lineage per source domain;
the fields for the other domains are `None`.

| Group | Fields |
| ----- | ------ |
| book | `book_id`, `book_title`, `edition_id`, `edition_title`, `chapter_id`, `chapter_title`, `section_id`, `section_title`, `page_start`, `page_end`, `page` |
| quran | `surah_id`, `surah_number`, `surah_name`, `ayah_id`, `ayah_number`, `translation_language`, `translator` |
| hadith | `collection_id`, `collection_name`, `hadith_book_id`, `hadith_book_name`, `hadith_chapter_id`, `hadith_chapter_name`, `hadith_id`, `hadith_number` |
| origin | `source_file_id`, `source_sha256` (always present) |

Common to every citation: `source_type` (`book` | `quran` | hadith-equivalent
`hadith`), `content_id`, `chunk_id`, and the two origin fields.

Every builder guarantees values match the actual rows:

- `citation_from_chunk(chunk)` — book lineage via `chunk.book`,
  `book.edition`, and the chapter/section rows resolved from the chunk's FKs.
- `citation_from_ayah(ayah)` / `citation_from_translation(translation)` —
  Quran lineage; the translation citation preserves the ayah lineage.
- `citation_from_hadith(hadith)` — collection → hadith book → chapter →
  number.
- `citation_from_db(record)` — dispatches on record type.

Builders raise `TypeError` for records of any other type, so a citation can
never be fabricated for a record that doesn't exist in the database.

## Methods

- `to_dict()` — flat mapping with a stable key set; `None` for absent fields.
- `to_json()` — `json.dumps(..., ensure_ascii=False)`.
- `reference()` — compact human-readable string, e.g.
  - `البقرة:255`
  - `البقرة:255 (en by Pickthall)`
  - `Sahih al-Bukhari #7, Kitab al-Iman`
  - `tadhkirah of ibn mulaqqin, ch. Chapter One, Section Alpha, p. 12`

## CLI

```pwsh
knowledge-base cite 8e3ba214de62 --limit 3
knowledge-base cite 8e3ba214de62 --limit 1 --json
```

Lists one citation per content chunk of the source file matching the given
sha256 prefix: reference line plus source sha, page, chunk id, and content id.
`--json` prints the full `Citation` records as a JSON array.

## Invariants

- Citations originate from DB rows only; foreign ORM objects raise `TypeError`.
- The JSON key set is stable — consumers can rely on the contract.
- `source_sha256` always resolves to the `source_files` row behind the record.