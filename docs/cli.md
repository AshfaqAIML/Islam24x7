# `kb` — knowledge-base CLI

`kb` is a small, high-level command line interface over the whole system:
import, inspect, process, search, embed, reindex, validate, retry, export,
and check status/stats. It wraps the same engines as the granular
`knowledge-base` CLI (`pipeline run`, `index run`, `embed run`, …) behind one
consistent surface.

```pwsh
kb --help                # all commands
kb <command> --help      # options for one command
kb --version
```

Configuration comes from the same `KB_*` env vars / `.env` that the rest of
the system uses (`KB_DATA_DIR`, `KB_DATABASE_URL`, …).

Global options (may appear before or after the command):

| option | meaning |
| --- | --- |
| `-v, --verbose` | increase log verbosity (repeat for `DEBUG`) |
| `-q, --quiet` | suppress progress output and colour |
| `--log-level LEVEL` | override log level (`TRACE`…`CRITICAL`) |
| `--log-file PATH` | also write logs to a file |
| `--json` | print machine-readable JSON instead of a table |

Exit codes: `0` success, `1` command failed / validation found criticals /
import quarantined something, `2` invalid arguments, `3` (reserved) the
pipeline stopped waiting on review.

## Commands

### `kb inspect <file.pdf>`

Classify a raw PDF — text, scanned, or mixed — and guess its language from a
sample of text pages.

### `kb import <path>...`

Register files or directories under `data/raw`. Re-imports are detected by
content hash and reported as duplicates. `--dry-run` hashes without writing.

```pwsh
kb import "Books" --category books
kb import "Books/sample.pdf" --dry-run
```

### `kb process`

Run the end-to-end pipeline
(`inspect → extract → ocr → metadata → publish → structure → normalize →
chunk → index → embed`) for one source, an ingested file, failed/pending
sources, or everything.

```pwsh
kb process --sha256 8e3ba214de62           # one source
kb process --source "Books/sample.pdf"     # import first, then process
kb process --pending --limit 5             # sources that stalled or failed
kb process --all --auto-review             # everything, auto-approve + publish
kb process --sha256 8e3ba21 --from structure --force   # resume a stage
kb process --dry-run                       # preview what would run
```

`--auto-review` is the default; use `--no-auto-review` to stop at the
review/publish gate and let a human approve candidates first. `--ocr-engine`
and `--embed-provider` select overrides; `--until STAGE` caps the plan.

### `kb validate [--sha256 <prefix> | --book <uuid>]`

Check knowledge-base integrity: content chains, chunk presence, search
documents, embeddings, and orphaned rows. With no selector, validates every
published book. Returns `1` when critical issues are found.

### `kb search <query> [--domains …]`

Full-text search with domain filters:

```pwsh
kb search "patience and perseverance"
kb search "الصبر" --language ar
kb search "tadhkirah" --book 8e3ba21 --author "ibn mulaqqin"
kb search "fiqh" --category fiqh --limit 5
kb search "sabr" --all-terms --domains content hadith
```

### `kb ask <question> [filters]`

Source-grounded question answering (RAG): retrieves passages with hybrid
keyword + semantic search, then produces an extractive answer that cites its
sources `[S1] … [Sn]`. Every citation is rebuilt from the stored chunk row.

```pwsh
kb ask "What is mufradat hadith?"
kb ask "ما هو الصبر" --language ar
kb ask "How are narrator chains classified?" --limit 5
kb ask "What did ibn mulaqqin say about tadlis?" --book 8e3ba21
```

The output shows a `GROUNDED`/`UNGROUNDED` badge — a verdict from
`verify_grounding` on how many answer sentences carry a valid citation mask,
plus the sources and retrieval/generation timings. `--json` prints the full
answer payload (question, answer, sources, notes, timings).

### `kb embed [--sha256 <prefix> | --all]`

Generate chunk embeddings (incremental — unchanged chunks are reused).
`--provider`, `--model`, `--model-version`, `--dimensions`, `--batch-size`
override the configured embedding settings.

### `kb reindex [--sha256 <prefix> | --all]`

Rebuild the full-text `search_documents` for published books.

### `kb status`

Dashboard of the knowledge base: sources, books, chunks, embeddings, search
documents, Quran/hadith counts, plus job status and completed-work breakdowns.

### `kb retry [--sha256 <prefix> | --all]`

Re-run the pipeline for sources whose jobs failed or never started — handy
after `kb import` of a batch that didn't finish processing.

### `kb stats`

Aggregate statistics: books by category, sources by format, average tokens and
pages per chunk.

### `kb export [--sha256 <prefix> | --book <uuid> | --all]`

Export each book's metadata and chunks to a JSON file under
`--out <dir>` (default `data/exports`).

### `kb serve [--host <addr>] [--port <port>] [--reload]`

Run the HTTP API (uvicorn) exposing the knowledge base over JSON:

- `GET  /health` — liveness probe
- `GET  /status` — dashboard counts
- `POST /ask`    — source-grounded RAG answer (`{"question": "…", "k": 5}`)
- `POST /search` — full-text search (`{"query": "…", "limit": 10}`)

```pwsh
kb serve --host 127.0.0.1 --port 8000
```

## Testing

`tests/test_kb_cli.py` covers parsing, dispatch, dry-runs, and exit codes
against the shared test database.

## Relationship to `knowledge-base`

`kb` is the task-oriented surface; the existing `knowledge-base` CLI remains for
granular, stage-by-stage work (say, `knowledge-base metadata review` or
`knowledge-base structure detect`). Both share engine and settings code — `kb`
never re-implements pipeline logic.