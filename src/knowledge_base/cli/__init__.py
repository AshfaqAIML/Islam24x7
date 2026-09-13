"""Command-line interface for the Islamic Knowledge Base.

Entry points:
- ``knowledge_base.cli:main`` (console script ``knowledge-base``)
- ``python -m knowledge_base``
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from knowledge_base import __version__
from knowledge_base.config import get_settings
from knowledge_base.logging import configure_logging

_EPILOG = "Configure via KB_* env vars or a local .env file (see .env.example)."


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledge-base",
        description="Local, Python-based Islamic Knowledge Base.",
        epilog=_EPILOG,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        help="override the configured log level",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="Print the installed version")

    env = sub.add_parser("env", help="Show the resolved configuration")
    env.add_argument("--as-json", action="store_true", help="print config as JSON")

    glob = sub.add_parser("glob", help="List files under the data directory")
    glob.add_argument("pattern", nargs="?", default="*", help="glob pattern (default: *)")

    norm = sub.add_parser(
        "normalize",
        help="Normalize text: file utility or pipeline run for a published book",
    )
    n_sub = norm.add_subparsers(dest="normalize_command", required=True)

    n_file = n_sub.add_parser(
        "file",
        help="Normalize a plain-text file and write a report under data/processed/normalized",
    )
    n_file.add_argument("file", type=Path, help="path to a source text file")
    n_file.add_argument(
        "--config",
        choices=["conservative", "search"],
        default="search",
        help="normalization configuration to apply (default: search)",
    )

    n_run = n_sub.add_parser(
        "run",
        help="Derive search-normalized text for a published book's content blocks",
    )
    n_run.add_argument("--sha256", help="normalize one book by source sha256 prefix")
    n_run.add_argument(
        "--all", dest="norm_all", action="store_true", help="normalize all published books"
    )
    n_run.add_argument(
        "--limit", type=int, default=None, help="cap the number of books with --all"
    )
    n_run.add_argument(
        "--config",
        choices=["auto", "conservative", "search"],
        default="auto",
        help="config override (default: auto per book language)",
    )

    ingest = sub.add_parser(
        "ingest",
        help="Register files from a directory into the knowledge base",
    )
    ingest.add_argument("dir", type=Path, help="directory tree containing source files")
    ingest.add_argument(
        "--category",
        default="books",
        help="subdirectory under data/raw to store ingested files (default: books)",
    )
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        help="hash and report without writing anything",
    )

    inspect = sub.add_parser(
        "inspect",
        help="Classify registered PDFs (text layer / OCR need / language)",
    )
    inspect.add_argument("--sha256", help="inspect one source by sha256 prefix")
    inspect.add_argument(
        "--all", dest="inspect_all", action="store_true", help="inspect all registered sources"
    )
    inspect.add_argument(
        "--limit", type=int, default=None, help="cap the number of files with --all"
    )

    extract = sub.add_parser(
        "extract",
        help="Extract page-by-page text from PDFs with a text layer",
    )
    extract.add_argument("--sha256", help="extract one source by sha256 prefix")
    extract.add_argument(
        "--all", dest="extract_all", action="store_true", help="extract all text-layer sources"
    )
    extract.add_argument(
        "--limit", type=int, default=None, help="cap the number of files with --all"
    )
    extract.add_argument(
        "--force", action="store_true", help="extract scanned sources too (empty pages)"
    )

    ocr = sub.add_parser(
        "ocr",
        help="OCR scanned pages; record engine, confidence, and review flags",
    )
    ocr.add_argument("--sha256", help="ocr one source by sha256 prefix")
    ocr.add_argument("--all", dest="ocr_all", action="store_true", help="ocr all sources")
    ocr.add_argument("--limit", type=int, default=None, help="cap the number of files with --all")
    ocr.add_argument("--force", action="store_true", help="re-OCR pages already processed")
    ocr.add_argument("--engine", default=None, help="tesseract | easyocr | dummy")
    ocr.add_argument("--dpi", type=int, default=None, help="render resolution (default 300)")
    ocr.add_argument("--languages", default=None, help="comma list, e.g. ar,ur or en,ar")

    meta = sub.add_parser(
        "metadata",
        help="Extract, review, and publish book metadata candidates",
    )
    meta_sub = meta.add_subparsers(dest="meta_command", required=True)

    meta_extract = meta_sub.add_parser(
        "extract",
        help="Extract metadata candidates from registered sources",
    )
    meta_extract.add_argument("--sha256", help="extract one source by sha256 prefix")
    meta_extract.add_argument(
        "--all", dest="meta_all", action="store_true", help="extract for all sources"
    )
    meta_extract.add_argument(
        "--limit", type=int, default=None, help="cap the number of files with --all"
    )
    meta_extract.add_argument(
        "--pages", type=int, default=None, help="how many leading pages to scan (default 5)"
    )
    meta_extract.add_argument(
        "--no-filename",
        action="store_true",
        help="do not seed low-confidence title guesses from filenames",
    )
    meta_extract.add_argument(
        "--user-json",
        type=Path,
        default=None,
        help="json file of explicit field values: {\"title\": \"...\", ...}",
    )

    meta_show = meta_sub.add_parser(
        "show",
        help="Show the merged best-guess metadata for a source",
    )
    meta_show.add_argument("--sha256", required=True, help="source sha256 prefix")

    meta_review = meta_sub.add_parser(
        "review",
        help="List / approve / reject metadata candidates, then publish approved",
    )
    meta_review.add_argument("--sha256", required=True, help="source sha256 prefix")
    meta_review.add_argument("--approve", help="field to approve (e.g. title, author)")
    meta_review.add_argument(
        "--reject", help="field whose best candidate should be rejected"
    )
    meta_review.add_argument(
        "--value", help="corrected value to use when approving a field"
    )
    meta_review.add_argument("--note", help="review note")
    meta_review.add_argument(
        "--reviewer", default="cli", help="human identity recording this review"
    )
    meta_review.add_argument(
        "--publish",
        action="store_true",
        help="materialize approved fields into source_editions + books",
    )

    structure = sub.add_parser(
        "structure",
        help="Detect, inspect, and review book structure",
    )
    str_sub = structure.add_subparsers(dest="structure_command", required=True)

    str_detect = str_sub.add_parser(
        "detect",
        help="Detect structure for a published book's extraction output",
    )
    str_detect.add_argument("--sha256", help="detect one book by source sha256 prefix")
    str_detect.add_argument(
        "--all", dest="str_all", action="store_true", help="detect for all published books"
    )
    str_detect.add_argument(
        "--limit", type=int, default=None, help="cap the number of books with --all"
    )

    str_show = str_sub.add_parser(
        "show",
        help="Show the detected structure of a book from the database",
    )
    str_show.add_argument("--sha256", required=True, help="source sha256 prefix")

    str_review = str_sub.add_parser(
        "review",
        help="List flagged blocks and approve / reject them",
    )
    str_review.add_argument("--sha256", required=True, help="source sha256 prefix")
    str_review.add_argument(
        "--list", dest="str_list", action="store_true", help="list flagged blocks"
    )
    str_review.add_argument(
        "--approve", metavar="PAGE:SEQ", help="approve a flagged block (e.g. 3:12)"
    )
    str_review.add_argument(
        "--reject", metavar="PAGE:SEQ", help="reject a flagged block (e.g. 3:12)"
    )
    str_review.add_argument("--note", help="review note")
    str_review.add_argument(
        "--reviewer", default="cli", help="human identity recording this review"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns a process exit code."""
    args = _build_parser().parse_args(argv)
    settings = get_settings()

    level = args.log_level if args.log_level is not None else settings.log_level
    try:
        configure_logging(level)
    except ValueError as exc:  # pragma: no cover - trivial guard
        print(f"error: {exc}", file=sys.stderr)
        return 2

    from knowledge_base.cli import commands

    command = args.command
    if command == "version":
        commands.cmd_version()
    elif command == "env":
        commands.cmd_env(as_json=args.as_json)
    elif command == "glob":
        commands.cmd_glob(pattern=args.pattern)
    elif command == "normalize":
        if args.normalize_command == "file":
            return commands.cmd_normalize(args.file, args.config)
        if args.normalize_command == "run":
            return commands.cmd_normalize_run(
                args.sha256,
                normalize_all_=args.norm_all,
                limit=args.limit,
                config_name=args.config,
            )
    elif command == "ingest":
        return commands.cmd_ingest(args.dir, args.category, dry_run=args.dry_run)
    elif command == "inspect":
        return commands.cmd_inspect(
            args.sha256, inspect_all=args.inspect_all, limit=args.limit
        )
    elif command == "extract":
        return commands.cmd_extract(
            args.sha256,
            extract_all=args.extract_all,
            limit=args.limit,
            force=args.force,
        )
    elif command == "ocr":
        return commands.cmd_ocr(
            args.sha256,
            ocr_all=args.ocr_all,
            limit=args.limit,
            force=args.force,
            engine=args.engine,
            dpi=args.dpi,
            languages=args.languages,
        )
    elif command == "metadata":
        if args.meta_command == "extract":
            return commands.cmd_metadata_extract(
                args.sha256,
                metadata_all=args.meta_all,
                limit=args.limit,
                pages=args.pages,
                use_filename=not args.no_filename,
                user_json=args.user_json,
            )
        if args.meta_command == "show":
            return commands.cmd_metadata_show(args.sha256)
        if args.meta_command == "review":
            return commands.cmd_metadata_review(
                args.sha256,
                approve=args.approve,
                reject=args.reject,
                value=args.value,
                note=args.note,
                reviewer=args.reviewer,
                publish=args.publish,
            )
    elif command == "structure":
        if args.structure_command == "detect":
            return commands.cmd_structure_detect(
                args.sha256, structure_all=args.str_all, limit=args.limit
            )
        if args.structure_command == "show":
            return commands.cmd_structure_show(args.sha256)
        if args.structure_command == "review":
            return commands.cmd_structure_review(
                args.sha256,
                list_blocks=args.str_list,
                approve=args.approve,
                reject=args.reject,
                note=args.note,
                reviewer=args.reviewer,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
