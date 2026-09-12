# raw/quran/

Authoritative Quran source material — never modified. A file here belongs to
one of these reference kinds:

- Canonical mushaf text (Uthmani/Rasm scripts) — Arabic
- Authenticated translations (per-ayah, with translator attribution)
- Quran recitation metadata / audio references (rare)

## Conventions

- One source per file, named descriptively (e.g. `quran-uthmani.txt`,
  `mushaf-tajweed.json`).
- Translations must carry translator and edition metadata; the pipeline records
  it in `source_editions`.
- Ayah-level data should use standard identifiers: surah number + ayah number
  (e.g. `2:255` for Ayat al-Kursi).

## Rules

- This content is religious ground truth. The pipeline **never writes into**
  this directory and **never "corrects"** the text.
- Derived ayah/chunk data is produced under `data/processed/` and validated
  against this source — reconstruction is never delegated to an LLM.