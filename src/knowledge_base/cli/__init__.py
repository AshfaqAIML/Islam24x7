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
        help="Normalize a plain-text file and write a report under data/processed/normalized",
    )
    norm.add_argument("file", type=Path, help="path to a source text file")
    norm.add_argument(
        "--config",
        choices=["conservative", "search"],
        default="search",
        help="normalization configuration to apply (default: search)",
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
        return commands.cmd_normalize(args.file, args.config)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
