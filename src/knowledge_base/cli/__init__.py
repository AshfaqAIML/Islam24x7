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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
