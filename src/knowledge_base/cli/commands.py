"""CLI command implementations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from knowledge_base import __version__
from knowledge_base.config import Settings, get_settings
from knowledge_base.core.hashing import sha256_file
from knowledge_base.normalization import (
    conservative_config,
    normalize_text,
    search_config,
    write_report,
)


def _settings() -> Settings:
    return get_settings()


def cmd_version() -> None:
    """Print the installed package version."""
    print(f"knowledge-base {__version__}")


def cmd_env(*, as_json: bool = False) -> None:
    """Print the resolved configuration."""
    settings = _settings()
    data = {
        "package_version": __version__,
        "data_dir": str(settings.data_dir.resolve()),
        "log_level": settings.log_level,
        "database_url": settings.database_url or "(not configured)",
        "test_database_url": settings.test_database_url or "(not configured)",
    }
    if as_json:
        print(json.dumps(data, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")


def cmd_glob(*, pattern: str) -> None:
    """List files under the data directory matching the given glob."""
    from knowledge_base.logging import logger

    root = _settings().data_dir
    if not root.is_dir():
        print(f"Data directory does not exist: {root}", file=sys.stderr)
        return
    hits = sorted(str(p.relative_to(root)) for p in root.glob(pattern))
    for entry in hits:
        logger.debug("found {}", entry)
        print(entry)


def cmd_normalize(file: Path, config_name: str) -> int:
    """Normalize a plain-text file and write a normalization report."""
    from knowledge_base.logging import logger

    if not file.is_file():
        print(f"File not found: {file}", file=sys.stderr)
        return 1

    config = search_config() if config_name == "search" else conservative_config()
    text = file.read_text(encoding="utf-8")
    result = normalize_text(text, config)

    from knowledge_base.normalization import NormalizationItem, NormalizationReport

    item = NormalizationItem(
        source_file_id=sha256_file(file),
        page_number=1,
        text=text,
        result=result,
    )
    report = NormalizationReport(source_file_id=item.source_file_id, items=[item])
    json_path, _ = write_report(report, _settings().data_dir)
    logger.info("Normalization complete for {}", file.name)
    print(f"source_id: {item.source_file_id}")
    print(f"unchanged: {result.unchanged}")
    print(f"protected: {result.stats.protected}")
    print(f"report:    {json_path}")
    return 0


def cmd_ingest(source_dir: Path, category: str, *, dry_run: bool = False) -> int:
    """Register every source file under ``source_dir`` into the KB database."""
    from collections import Counter

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.ingest.ingest import ingest_directory

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        results = ingest_directory(
            source_dir,
            session=session,
            category=category,
            dry_run=dry_run,
            settings=settings,
        )

    summary = Counter(r.status for r in results)
    logger.info("Ingestion finished: {}", dict(summary))
    for status, count in summary.most_common():
        print(f"{status:14s} {count}")
    if results and summary["failed"]:
        print("failures:", file=sys.stderr)
        for result in results:
            if result.status == "failed":
                print(f"  {result.path}: {result.reason}", file=sys.stderr)
    return 0


__all__ = ["cmd_env", "cmd_glob", "cmd_ingest", "cmd_normalize", "cmd_version"]
