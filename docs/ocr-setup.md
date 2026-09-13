# OCR Setup

**Status:** Implemented (migration `75a57d77d004_add_ocr_results`).

The OCR stage turns scanned and mixed books into searchable text. It never
touches the source PDFs: only the pages that still need text are rendered, and
results are stored under `data/processed/ocr/<sha256>/` in two separate trees:

- `text/<page>.txt` — recognized text (one file per PDF page number), and
- `render/<page>.png` — the rendered page image used by the OCR engine.

Per-page results are also recorded in the `ocr_pages` table (one row per
`(source_file_id, page_number)`), and the run summary is persisted in the
`processing_jobs` manifest with key `type = ocr`.

## Which pages get OCR'd

`plan_ocr_pages` decides which PDF page numbers to process:

1. From the inspection report (`data/processed/inspect/<sha256>.json`), every
   page flagged `scanned` is required, plus any archived page whose text was
   garbled.
2. From the extraction index (`data/processed/extract/<sha256>/index.json`),
   every page without an extracted text file (garbled glyphs, scanned pages,
   blank leaves) is required.
3. If neither stage produced artifacts for the file, every page is required.

So a `text_pdf` with a clean layer is skipped entirely, while a `mixed_pdf`
(Nuzhat volumes) OCRs only its scanned/garbled pages.

## Installing Tesseract (default engine)

The default engine is **Tesseract**. It is an external program and must be
installed on the PATH.

### Windows

1. Install a Tesseract build, e.g. from
   <https://github.com/UB-Mannheim/tesseract/wiki> (or `choco install tesseract`).
2. Add `C:\Program Files\Tesseract-OCR` to your `PATH`.
3. Install language data if your installer did not bundle it. The project
   needs `ara` (Arabic) and optionally `urd` (Urdu). Put the files in the
   `tessdata` directory next to the binary:
   - `ara.traineddata` and `urd.traineddata` from
     <https://github.com/tesseract-ocr/tessdata_fast> (fast) or
     <https://github.com/tesseract-ocr/tessdata> (best quality), and
   - `osd.traineddata` (needed for page layout detection).

### macOS (Homebrew)

```sh
brew install tesseract tesseract-lang
```

### Ubuntu / Debian

```sh
sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-urd
```

### Verify

```sh
tesseract --version
tesseract --list-langs   # must show ara (and urd if used)
```

## Installing the Python packages

The engine bindings are imported lazily, so the CLI works even before they are
installed; a run that needs them fails with a clear `engine unavailable`
message instead of crashing.

```sh
.venv\Scripts\pip install pytesseract pillow
```

EasyOCR (Chinese/Urdu/English multilanguage, pure-Python, downloads its own
models) is supported as an alternative:

```sh
.venv\Scripts\pip install easyocr
```

## Running OCR

```sh
# one book identified by sha256 prefix
set KB_DATABASE_URL=postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base
.venv\Scripts\knowledge-base.exe ocr --sha256 1f2a3b

# all books without a successful OCR run, capped
.venv\Scripts\knowledge-base.exe ocr --all --limit 20

# force re-OCR of a book, Arabic + Urdu training
.venv\Scripts\knowledge-base.exe ocr --sha256 1f2a3b --force --languages ar,ur

# higher render resolution (default 300 dpi)
.venv\Scripts\knowledge-base.exe ocr --all --dpi 400
```

Use the `dummy` engine for a smoke test without any external software:

```sh
.venv\Scripts\knowledge-base.exe ocr --sha256 1f2a3b --engine dummy
```

The exit code is `0` on success, `3` when the requested engine is unavailable,
and `1` on other errors.

## Quality assessment

Each page is graded after OCR:

| Status  | Meaning |
| ------- | ------- |
| `ok`    | usable text, no warnings |
| `review`| flagged for human review (empty text, low confidence, too short, or low alpha ratio) |
| `failed`| OCR or rendering raised an error; `error` column carries the detail |

Nothing is silently corrected: results are always stored as produced by the
engine, and `review`/`failed` pages are surfaced in the run summary
(`report.txt` / `report.json` under `data/processed/ocr/<sha256>/`).