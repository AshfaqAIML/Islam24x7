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


def cmd_inspect(sha256: str | None, *, inspect_all: bool = False, limit: int | None = None) -> int:
    """Classify registered PDFs; print a compact summary per file."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.inspect.inspect import inspect_all as run_all
    from knowledge_base.pipeline.inspect.inspect import inspect_file

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    report_dir = settings.data_dir / "processed" / "inspect"

    with session_scope(factory) as session:
        if sha256:
            source = session.scalar(
                select(SourceFile).where(SourceFile.sha256.startswith(sha256))
            )
            if source is None:
                print(f"No source matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                inspect_file(
                    source,
                    session=session,
                    report_dir=report_dir,
                    data_dir=settings.data_dir,
                )
            ]
        elif inspect_all:
            results = run_all(session, settings=settings, limit=limit)
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        pages = result.page_count
        label = result.classification.value.upper()
        logger.info(
            "inspect {} pages={} text={} scanned={} class={} lang={}",
            result.sha256[:12],
            pages,
            result.text_pages,
            result.scanned_pages,
            label,
            result.language_hint or "-",
        )
        print(
            f"{label:11s} {result.sha256[:12]} pages={pages:<5d} "
            f"text={result.text_pages}/{pages} scanned={result.scanned_pages}"
            f"  lang={result.language_hint or '-':<2s}  {result.summary_path or result.error}"
        )
    return 0


def cmd_extract(
    sha256: str | None, *, extract_all: bool = False, limit: int | None = None, force: bool = False
) -> int:
    """Extract page text from registered PDFs with a text layer."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.extract.extract import extract_all as run_all
    from knowledge_base.pipeline.extract.extract import extract_file

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    output_root = settings.data_dir / "processed" / "extract"

    with session_scope(factory) as session:
        if sha256:
            source = session.scalar(
                select(SourceFile).where(SourceFile.sha256.startswith(sha256))
            )
            if source is None:
                print(f"No source matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                extract_file(
                    source,
                    session=session,
                    output_dir=output_root / source.sha256,
                    data_dir=settings.data_dir,
                )
            ]
        elif extract_all:
            results = run_all(session, settings=settings, limit=limit, force=force)
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        status = result.error or "ok"
        logger.info("extract {} pages={} text={} {}", result.sha256[:12],
                    result.page_count, f"{result.pages_with_text}/{result.page_count}", status)
        print(
            f"{result.sha256[:12]:12s} pages={result.page_count:<5d} "
            f"text={result.pages_with_text}/{result.page_count}  {status}"
        )
    return 0


__all__ = [
    "cmd_env",
    "cmd_glob",
    "cmd_ingest",
    "cmd_inspect",
    "cmd_extract",
    "cmd_normalize",
    "cmd_version",
]
