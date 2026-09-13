"""Command-line interface for the Islamic Knowledge Base (``kb``).

A small, high-level CLI for operating the whole system: import files,
inspect them, run the processing pipeline, search, embed, reindex, validate,
retry, export, and check status/stats.

Exit codes:
    0  success
    1  command failed / validation found issues / quarantine happened
    2  invalid arguments or configuration
    3  pipeline stopped waiting on interactive review
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from knowledge_base import __version__
from knowledge_base.config import get_settings
from knowledge_base.logging import configure_logging

_EPILOG = (
    "Configure via KB_* env vars (KB_DATA_DIR, KB_DATABASE_URL) or a local "
    ".env file. Run 'kb <command> --help' for details."
)

_CONFIG_LEVELS = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kb",
        description="Islamic Knowledge Base — process, search, and retrieve from local books.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase log verbosity (can be repeated)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress progress output and colour",
    )
    parser.add_argument(
        "--log-level",
        choices=_CONFIG_LEVELS,
        default=None,
        help="override the configured log level",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="also write logs to this file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json_global",
        help="print machine-readable JSON instead of a table",
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # inspect ---------------------------------------------------------------
    inspect = sub.add_parser(
        "inspect", help="Classify a raw file (text / scanned / mixed, language hint)"
    )
    inspect.add_argument("path", type=Path, help="path to a PDF file")

    # import ----------------------------------------------------------------
    imp = sub.add_parser("import", help="Register files or directories into the knowledge base")
    imp.add_argument("paths", type=Path, nargs="+", help="file or directory to import")
    imp.add_argument(
        "--category", default="books", help="category folder under data/raw (default: books)"
    )
    imp.add_argument(
        "--dry-run", action="store_true", help="hash and preview without writing anything"
    )

    # process ---------------------------------------------------------------
    proc = sub.add_parser("process", help="Run the end-to-end processing pipeline")
    proc.add_argument("--sha256", help="process one source by sha256 prefix")
    proc.add_argument(
        "--source", dest="source_path", type=Path, help="import a raw file first, then process it"
    )
    proc.add_argument(
        "--pending", action="store_true", help="process sources that have failed or never started"
    )
    proc.add_argument(
        "--all", dest="process_all", action="store_true", help="process every registered source"
    )
    proc.add_argument(
        "--limit", type=int, default=None, help="cap the number of sources (with --all/--pending)"
    )
    proc.add_argument(
        "--no-auto-review",
        dest="auto_review",
        action="store_false",
        help="stop at the review/publish gate instead of auto-approving",
    )
    proc.add_argument(
        "--force", action="store_true", help="re-run stages even if already completed"
    )
    proc.add_argument(
        "--continue-on-error", action="store_true", help="keep going after a failed stage"
    )
    proc.add_argument(
        "--from", dest="start_from", default=None, help="start at this stage (resume)"
    )
    proc.add_argument("--until", dest="stop_at", default=None, help="stop after this stage")
    proc.add_argument(
        "--ocr-engine",
        default=None,
        help="ocr engine (tesseract, easyocr, dummy, or pkg.module:Cls)",
    )
    proc.add_argument(
        "--embed-provider", default=None, help="embedding provider name (default: settings)"
    )
    proc.add_argument(
        "--dry-run", action="store_true", help="preview which sources/stages would run"
    )

    # validate --------------------------------------------------------------
    val = sub.add_parser(
        "validate", help="Check knowledge-base integrity (chains, orphans, invariants)"
    )
    val.add_argument("--sha256", help="validate one source by sha256 prefix")
    val.add_argument("--book", dest="book_id", help="validate one book by UUID")

    # search ----------------------------------------------------------------
    search = sub.add_parser(
        "search", help="Full-text search across books, content, Quran, and hadith"
    )
    search.add_argument("query", help='keywords and/or quoted "exact phrase"')
    search.add_argument(
        "--domains",
        nargs="+",
        choices=["book", "chapter", "section", "content", "quran", "hadith"],
        default=None,
        help="domains to search (default: all)",
    )
    search.add_argument(
        "--all-terms", action="store_true", help="require every keyword (AND instead of OR)"
    )
    search.add_argument(
        "--language", choices=["ar", "ur", "en"], default=None, help="restrict by language"
    )
    search.add_argument("--category", help="category code (e.g. fiqh, tafsir)")
    search.add_argument("--book", dest="source", help="source sha256 prefix")
    search.add_argument("--author", help="author name substring")
    search.add_argument("--limit", type=int, default=20, help="max results (default 20)")

    # embed -----------------------------------------------------------------
    embed = sub.add_parser("embed", help="Generate chunk embeddings for vector search")
    embed.add_argument("--sha256", help="embed one source by sha256 prefix")
    embed.add_argument(
        "--all", dest="embed_all", action="store_true", help="embed all published books"
    )
    embed.add_argument("--limit", type=int, default=None, help="cap the number of books with --all")
    embed.add_argument("--provider", default=None, help="embedding provider")
    embed.add_argument("--model", default=None, help="embedding model name")
    embed.add_argument("--model-version", default=None, help="embedding model version")
    embed.add_argument("--dimensions", type=int, default=None, help="vector dimensions")
    embed.add_argument("--batch-size", type=int, default=None, help="provider batch size")

    # reindex ---------------------------------------------------------------
    reindex = sub.add_parser(
        "reindex", help="Rebuild full-text search documents for published books"
    )
    reindex.add_argument("--sha256", help="reindex one source by sha256 prefix")
    reindex.add_argument(
        "--all", dest="reindex_all", action="store_true", help="reindex all published books"
    )
    reindex.add_argument(
        "--limit", type=int, default=None, help="cap the number of books with --all"
    )

    # status ----------------------------------------------------------------
    sub.add_parser("status", help="Show a dashboard of the knowledge base")

    # retry -----------------------------------------------------------------
    retry = sub.add_parser("retry", help="Re-run failed or pending stages (resumable)")
    retry.add_argument("--sha256", help="retry one source by sha256 prefix")
    retry.add_argument(
        "--all",
        dest="retry_all",
        action="store_true",
        help="retry every source with failed/pending work",
    )

    # stats -----------------------------------------------------------------
    sub.add_parser("stats", help="Show aggregate statistics across the knowledge base")

    # export ----------------------------------------------------------------
    export = sub.add_parser("export", help="Export book metadata and chunks to JSON files")
    export.add_argument("--sha256", help="export one source by sha256 prefix")
    export.add_argument("--book", dest="book_id", help="export one book by UUID")
    export.add_argument(
        "--all", dest="export_all", action="store_true", help="export all published books"
    )
    export.add_argument(
        "--limit", type=int, default=None, help="cap the number of books with --all"
    )
    export.add_argument(
        "--out",
        dest="out_dir",
        type=Path,
        default=Path("data/exports"),
        help="output directory (default: data/exports)",
    )
    export.add_argument(
        "--format",
        dest="fmt",
        choices=["json"],
        default="json",
        help="export format (default: json)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``kb`` CLI; returns a process exit code."""
    args = _build_parser().parse_args(argv)
    settings = get_settings()

    level = args.log_level
    if level is None:
        level = settings.log_level
    if args.verbose >= 2:
        level = "DEBUG"
    elif args.verbose >= 1:
        level = "TRACE"
    if args.quiet and args.verbose == 0:
        level = "ERROR"

    args.as_json = bool(getattr(args, "as_json_global", False))

    try:
        configure_logging(level)
        if args.log_file is not None:
            from loguru import logger

            args.log_file.parent.mkdir(parents=True, exist_ok=True)
            logger.add(str(args.log_file), level="TRACE")
    except ValueError as exc:
        print(f"kb: error: {exc}", file=sys.stderr)
        return 2

    if getattr(args, "quiet", False):
        sys._kb_quiet = True  # type: ignore[attr-defined]

    from knowledge_base.cli.kb import commands

    cmd = args.command
    try:
        if cmd == "inspect":
            return commands.cmd_inspect(args.path, as_json=args.as_json)
        if cmd == "import":
            return commands.cmd_import(
                args.paths,
                category=args.category,
                dry_run=args.dry_run,
                as_json=args.as_json,
            )
        if cmd == "process":
            return commands.cmd_process(
                sha256=args.sha256,
                source_path=args.source_path,
                pending=args.pending,
                all_sources=args.process_all,
                limit=args.limit,
                force=args.force,
                auto_review=args.auto_review,
                continue_on_error=args.continue_on_error,
                start_from=args.start_from,
                stop_at=args.stop_at,
                ocr_engine=args.ocr_engine,
                embed_provider=args.embed_provider,
                dry_run=args.dry_run,
                as_json=args.as_json,
            )
        if cmd == "validate":
            return commands.cmd_validate(
                sha256=args.sha256, book_id=args.book_id, as_json=args.as_json
            )
        if cmd == "search":
            return commands.cmd_search(
                args.query,
                domains=tuple(args.domains) if args.domains else None,
                all_terms=args.all_terms,
                language=args.language,
                category=args.category,
                source=args.source,
                author=args.author,
                limit=args.limit,
                as_json=args.as_json,
            )
        if cmd == "embed":
            return commands.cmd_embed(
                sha256=args.sha256,
                all_sources=args.embed_all,
                limit=args.limit,
                provider_name=args.provider,
                model=args.model,
                model_version=args.model_version,
                dimensions=args.dimensions,
                batch_size=args.batch_size,
                as_json=args.as_json,
            )
        if cmd == "reindex":
            return commands.cmd_reindex(
                sha256=args.sha256,
                all_sources=args.reindex_all,
                limit=args.limit,
                as_json=args.as_json,
            )
        if cmd == "status":
            return commands.cmd_status(as_json=args.as_json)
        if cmd == "retry":
            return commands.cmd_retry(
                sha256=args.sha256,
                all_sources=args.retry_all,
                as_json=args.as_json,
            )
        if cmd == "stats":
            return commands.cmd_stats(as_json=args.as_json)
        if cmd == "export":
            return commands.cmd_export(
                sha256=args.sha256,
                book_id=args.book_id,
                all_sources=args.export_all,
                limit=args.limit,
                out_dir=args.out_dir,
                fmt=args.fmt,
            )
    except KeyboardInterrupt:
        print("kb: interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level user-facing guard
        print(f"kb: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
