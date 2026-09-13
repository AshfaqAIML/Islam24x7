"""CLI command implementations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from knowledge_base import __version__
from knowledge_base.config import Settings, get_settings
from knowledge_base.core.hashing import sha256_file
from knowledge_base.normalization import (
    conservative_config,
    normalize_text,
    search_config,
    write_report,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from knowledge_base.database.models.sources import SourceFile


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


def cmd_normalize_run(
    sha256: str | None,
    *,
    normalize_all_: bool = False,
    limit: int | None = None,
    config_name: str = "auto",
) -> int:
    """Derive (and persist) search-normalized text for a book's content blocks."""
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.normalize.processor import (
        normalize_all,
        normalize_book,
    )

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        if sha256:
            book = _find_book(session, sha256)
            if book is None:
                print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                normalize_book(
                    book,
                    session=session,
                    data_dir=settings.data_dir,
                    config_name=config_name,
                )
            ]
        elif normalize_all_:
            results = normalize_all(
                session, settings=settings, config_name=config_name, limit=limit
            )
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        logger.info(
            "normalize {} lang={} config={} total={} normalized={} skipped={} "
            "protected={} changed={} unchanged={}",
            result.sha256[:12], result.language.value, result.config_name,
            result.blocks_total, result.blocks_normalized, result.blocks_skipped,
            result.blocks_protected, result.changed, result.unchanged,
        )
        print(
            f"{result.sha256[:12]:12s} lang={result.language.value:3s} "
            f"config={result.config_name:12s} total={result.blocks_total:<4d} "
            f"normalized={result.blocks_normalized:<4d} skipped={result.blocks_skipped:<3d} "
            f"protected={result.blocks_protected:<3d} changed={result.changed:<4d} "
            f"unchanged={result.unchanged}  {result.error or result.report_path}"
        )
    return 0


def cmd_chunk_run(
    sha256: str | None,
    *,
    chunk_all_: bool = False,
    limit: int | None = None,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> int:
    """Materialize structure-aware chunks for a book's paragraphs (idempotent)."""
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.chunk.config import ChunkConfig
    from knowledge_base.pipeline.chunk.processor import chunk_all, chunk_book

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    config = ChunkConfig(max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    with session_scope(factory) as session:
        if sha256:
            book = _find_book(session, sha256)
            if book is None:
                print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                chunk_book(book, session=session, data_dir=settings.data_dir, config=config)
            ]
        elif chunk_all_:
            results = chunk_all(session, settings=settings, config=config, limit=limit)
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        logger.info(
            "chunk {} lang={} max_tokens={} overlap={} chunks={} paragraphs={} tokens={}",
            result.sha256[:12], result.language.value, result.config.max_tokens,
            result.config.overlap_tokens, result.chunk_count, result.paragraph_count,
            result.token_total,
        )
        print(
            f"{result.sha256[:12]:12s} lang={result.language.value:3s} "
            f"max_tokens={result.config.max_tokens:<4d} overlap={result.config.overlap_tokens:<3d} "
            f"chunks={result.chunk_count:<4d} paragraphs={result.paragraph_count:<4d} "
            f"tokens={result.token_total:<5d} pages={result.page_start}..{result.page_end}  "
            f"{result.error or result.report_path}"
        )
    return 0


def cmd_index_run(
    sha256: str | None,
    *,
    index_all_: bool = False,
    limit: int | None = None,
) -> int:
    """Index a book's chunks as full-text search documents (idempotent)."""
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.index.index import index_all as run_all
    from knowledge_base.pipeline.index.index import index_book

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        if sha256:
            book = _find_book(session, sha256)
            if book is None:
                print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [index_book(book, session=session, data_dir=settings.data_dir)]
        elif index_all_:
            results = run_all(session, settings=settings, limit=limit)
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        logger.info(
            "index {} lang={} chunks={} documents={}",
            result.sha256[:12], result.language.value,
            result.chunk_count, result.document_count,
        )
        print(
            f"{result.sha256[:12]:12s} lang={result.language.value:3s} "
            f"chunks={result.chunk_count:<4d} documents={result.document_count:<4d}  "
            f"{result.error or result.report_path}"
        )
    return 0


def cmd_embed_run(
    sha256: str | None,
    *,
    embed_all_: bool = False,
    limit: int | None = None,
    provider_name: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
    dimensions: int | None = None,
    batch_size: int | None = None,
) -> int:
    """Generate embeddings for a book's chunks (idempotent, incremental)."""
    from dataclasses import replace

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.embed.config import EmbedConfig
    from knowledge_base.pipeline.embed.processor import embed_all as run_all
    from knowledge_base.pipeline.embed.processor import embed_book
    from knowledge_base.pipeline.embed.provider import (
        EmbeddingProviderUnavailable,
        build_provider,
    )

    settings = _settings()
    config = EmbedConfig.from_settings(settings)
    overrides: dict[str, Any] = {}
    if provider_name:
        overrides["provider_name"] = provider_name
    if model:
        overrides["model_name"] = model
    if model_version:
        overrides["model_version"] = model_version
    if dimensions:
        overrides["dimensions"] = dimensions
    if batch_size:
        overrides["batch_size"] = batch_size
    if overrides:
        config = replace(config, **overrides)

    try:
        provider = build_provider(config.provider_name, config)
    except EmbeddingProviderUnavailable as exc:
        print(f"embedding provider unavailable: {exc}", file=sys.stderr)
        return 3

    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        if sha256:
            book = _find_book(session, sha256)
            if book is None:
                print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                embed_book(
                    book, session=session, data_dir=settings.data_dir,
                    provider=provider, config=config,
                )
            ]
        elif embed_all_:
            results = run_all(
                session, settings=settings, provider=provider,
                config=config, limit=limit,
            )
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        logger.info(
            "embed {} model={} v{} dims={} chunks={} embedded={} updated={} reused={}",
            result.sha256[:12], result.model_name, result.model_version,
            result.dimensions, result.chunk_count, result.embedded_count,
            result.updated_count, result.reused_count,
        )
        print(
            f"{result.sha256[:12]:12s} model={result.model_name} "
            f"v{result.model_version} dims={result.dimensions:<4d} "
            f"chunks={result.chunk_count:<4d} embedded={result.embedded_count:<4d} "
            f"updated={result.updated_count:<3d} reused={result.reused_count:<3d}  "
            f"{result.error or result.report_path}"
        )
    return 0


def cmd_search(
    query: str,
    *,
    domains: tuple[str, ...] | None = None,
    all_terms: bool = False,
    language: str | None = None,
    category: str | None = None,
    source: str | None = None,
    author: str | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> int:
    """Run a full-text search and render the hits."""
    from dataclasses import asdict

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.search import SearchParams, search

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        params = SearchParams(
            query=query,
            all_terms=all_terms,
            language=language,
            category=category,
            source=source,
            author=author,
            limit=limit,
        )
        if domains is not None:
            params.domains = domains
        hits = search(session, params)

    if as_json:
        print(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=2))
    else:
        if not hits:
            print("No results found.")
            return 0
        for idx, hit in enumerate(hits, start=1):
            print(f"[{idx}] {hit.domain}  rank={hit.rank:.4f}  {hit.title}")
            if hit.book and hit.book != hit.title:
                print(f"    Book: {hit.book}")
            if hit.author:
                print(f"    Author: {hit.author}")
            if hit.chapter:
                print(f"    Chapter: {hit.chapter}")
            if hit.section and hit.domain != "section":
                print(f"    Section: {hit.section}")
            if hit.page:
                print(f"    Page: {hit.page}")
            if hit.citation:
                print(f"    {hit.citation}")
            text = (hit.snippet or hit.matched_text).strip().replace("\n", " ")
            if len(text) > 140:
                text = text[:137] + "..."
            print(f"    Matched: {text}")
    return 0


def cmd_similar(
    query: str,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
    category: str | None = None,
    source: str | None = None,
    language: str | None = None,
    source_type: str | None = None,
    author: str | None = None,
    min_score: float | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> int:
    """Run a semantic (vector) search and render the hits with provenance."""
    from dataclasses import asdict, replace

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.pipeline.embed.config import EmbedConfig
    from knowledge_base.pipeline.embed.provider import (
        EmbeddingProviderUnavailable,
        build_provider,
    )
    from knowledge_base.search import similar

    settings = _settings()
    config = EmbedConfig.from_settings(settings)
    overrides: dict[str, Any] = {}
    if provider_name:
        overrides["provider_name"] = provider_name
    if model:
        overrides["model_name"] = model
    if model_version:
        overrides["model_version"] = model_version
    if overrides:
        config = replace(config, **overrides)

    try:
        provider = build_provider(config.provider_name, config)
    except EmbeddingProviderUnavailable as exc:
        print(f"embedding provider unavailable: {exc}", file=sys.stderr)
        return 3

    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        try:
            hits = similar(
                session,
                query,
                provider,
                model_name=config.model_name,
                model_version=config.model_version,
                limit=limit,
                category=category,
                source=source,
                language=language,
                source_type=source_type,
                author=author,
                min_score=min_score,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if as_json:
        print(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=2))
    else:
        if not hits:
            print("No results found.")
            return 0
        for idx, hit in enumerate(hits, start=1):
            print(f"[{idx}] similarity={hit.score:.4f}  {hit.book}")
            if hit.author:
                print(f"    Author: {hit.author}")
            if hit.category:
                print(f"    Category: {hit.category}")
            if hit.chapter:
                print(f"    Chapter: {hit.chapter}")
            if hit.section:
                print(f"    Section: {hit.section}")
            if hit.page:
                print(f"    Page: {hit.page}")
            if hit.source:
                print(f"    Source: {hit.source[:12]}")
            if hit.source_type:
                print(f"    Type: {hit.source_type}")
            if hit.language:
                print(f"    Language: {hit.language}")
            print(f"    Chunk: {hit.chunk_id}")
            text = hit.text.strip().replace("\n", " ")
            if len(text) > 140:
                text = text[:137] + "..."
            print(f"    Text: {text}")
    return 0


def cmd_hybrid(
    query: str,
    *,
    weight_fts: float = 0.5,
    weight_vector: float = 0.5,
    provider_name: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
    category: str | None = None,
    source: str | None = None,
    language: str | None = None,
    source_type: str | None = None,
    author: str | None = None,
    min_score: float | None = None,
    limit: int = 20,
    as_json: bool = False,
) -> int:
    """Run a hybrid (keyword + semantic) search and render the hits."""
    from dataclasses import asdict, replace

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.pipeline.embed.config import EmbedConfig
    from knowledge_base.pipeline.embed.provider import (
        EmbeddingProviderUnavailable,
        build_provider,
    )
    from knowledge_base.search import hybrid_search

    settings = _settings()
    config = EmbedConfig.from_settings(settings)
    overrides: dict[str, Any] = {}
    if model:
        overrides["model_name"] = model
    if model_version:
        overrides["model_version"] = model_version
    if overrides:
        config = replace(config, **overrides)

    provider = None
    if weight_vector > 0:
        try:
            provider = build_provider(provider_name or config.provider_name, config)
        except EmbeddingProviderUnavailable as exc:
            print(f"warning: {exc}; falling back to keyword-only", file=sys.stderr)
    if provider is None and weight_vector > 0 and weight_fts <= 0:
        print("semantic path disabled and keyword path has zero weight", file=sys.stderr)
        return 4

    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        hits = hybrid_search(
            session,
            query,
            provider=provider,
            model_name=config.model_name,
            model_version=config.model_version,
            weight_fts=weight_fts,
            weight_vector=weight_vector,
            limit=limit,
            category=category,
            source=source,
            language=language,
            source_type=source_type,
            author=author,
            min_score=min_score,
        )

    if as_json:
        print(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=2))
    else:
        if not hits:
            print("No results found.")
            return 0
        for idx, hit in enumerate(hits, start=1):
            retr = "+".join(hit.retrievers)
            print(
                f"[{idx}] score={hit.score:.4f}  {hit.book}  "
                f"({retr}) fts={hit.fts_score or 0.0:.4f} "
                f"vec={hit.vector_score or 0.0:.4f}"
            )
            if hit.author:
                print(f"    Author: {hit.author}")
            if hit.category:
                print(f"    Category: {hit.category}")
            if hit.chapter:
                print(f"    Chapter: {hit.chapter}")
            if hit.section:
                print(f"    Section: {hit.section}")
            if hit.page:
                print(f"    Page: {hit.page}")
            if hit.source:
                print(f"    Source: {hit.source[:12]}")
            if hit.source_type:
                print(f"    Type: {hit.source_type}")
            if hit.language:
                print(f"    Language: {hit.language}")
            print(f"    Chunk: {hit.chunk_id}")
            text = hit.text.strip().replace("\n", " ")
            if len(text) > 140:
                text = text[:137] + "..."
            print(f"    Text: {text}")
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


def cmd_ocr(
    sha256: str | None,
    *,
    ocr_all: bool = False,
    limit: int | None = None,
    force: bool = False,
    engine: str | None = None,
    dpi: int | None = None,
    languages: str | None = None,
) -> int:
    """OCR every page that needs it and record results + review flags."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.ocr.config import OcrConfig
    from knowledge_base.pipeline.ocr.engines import OcrEngineUnavailable, build_engine
    from knowledge_base.pipeline.ocr.processor import ocr_all as run_all
    from knowledge_base.pipeline.ocr.processor import ocr_file

    settings = _settings()
    engine_name = engine or "tesseract"
    config = OcrConfig(
        engine=engine_name,
        dpi=dpi or 300,
        languages=tuple(languages.split(",")) if languages else ("ar",),
    )
    try:
        backend = build_engine(engine_name, config)
    except OcrEngineUnavailable as exc:
        print(f"OCR engine unavailable: {exc}", file=sys.stderr)
        return 3

    kb_engine = create_app_engine(settings.database_url)
    factory = make_session_factory(kb_engine)

    with session_scope(factory) as session:
        if sha256:
            source = session.scalar(
                select(SourceFile).where(SourceFile.sha256.startswith(sha256))
            )
            if source is None:
                print(f"No source matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                ocr_file(
                    source,
                    session=session,
                    engine=backend,
                    config=config,
                    data_dir=settings.data_dir,
                    force=force,
                )
            ]
        elif ocr_all:
            results = run_all(
                session, settings=settings, engine=backend, config=config, limit=limit, force=force
            )
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        conf = f"{result.avg_confidence:.1f}" if result.avg_confidence is not None else "-"
        logger.info(
            "ocr {} engine={} ocr={} review={} failed={} conf={}",
            result.sha256[:12], result.engine, result.pages_ocr,
            result.pages_review, result.pages_failed, conf,
        )
        print(
            f"{result.sha256[:12]:12s} engine={result.engine:<9s} "
            f"ocr={result.pages_ocr:<4d} review={result.pages_review:<4d} "
            f"failed={result.pages_failed:<3d} conf={conf:<6s}  "
            f"{result.error or result.output_dir}"
        )
    return 0


def cmd_metadata_extract(
    sha256: str | None,
    *,
    metadata_all: bool = False,
    limit: int | None = None,
    pages: int | None = None,
    use_filename: bool = True,
    user_json: Path | None = None,
) -> int:
    """Extract metadata candidates and write the merge report per source."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.metadata.config import MetadataConfig
    from knowledge_base.pipeline.metadata.processor import extract_metadata, extract_metadata_all

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    config = MetadataConfig(
        scan_first_pages=pages if pages and pages > 0 else 5,
        use_filename=use_filename,
    )
    try:
        user_items = _load_user_items(user_json)
    except ValueError as exc:
        print(f"cannot load user metadata: {exc}", file=sys.stderr)
        return 1

    with session_scope(factory) as session:
        if sha256:
            source = session.scalar(
                select(SourceFile).where(SourceFile.sha256.startswith(sha256))
            )
            if source is None:
                print(f"No source matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [
                extract_metadata(
                    source,
                    session=session,
                    config=config,
                    data_dir=settings.data_dir,
                    user_items=user_items,
                )
            ]
        elif metadata_all:
            results = extract_metadata_all(
                session,
                settings=settings,
                config=config,
                limit=limit,
                user_items=user_items,
            )
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        overall = result.overall_confidence or "none"
        logger.info(
            "metadata {} fields={} conf={} review={}",
            result.sha256[:12], len(result.fields_found), overall, result.review_needed,
        )
        print(
            f"{result.sha256[:12]:12s} fields={len(result.fields_found):<2d} "
            f"conf={overall:<6s} review={result.review_needed}  "
            f"{result.error or result.summary_path}"
        )
    return 0


def cmd_metadata_show(sha256: str) -> int:
    """Print the merged best-guess metadata for one source."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.enums import MetadataField
    from knowledge_base.database.models.metadata import MetadataCandidate
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.pipeline.metadata.config import DEFAULT_METADATA_CONFIG
    from knowledge_base.pipeline.metadata.processor import (
        merge_candidates,
        overall_confidence,
        render_report_text,
    )

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        source = session.scalar(
            select(SourceFile).where(SourceFile.sha256.startswith(sha256))
        )
        if source is None:
            print(f"No source matching sha256 prefix {sha256!r}", file=sys.stderr)
            return 1
        rows = session.scalars(
            select(MetadataCandidate).where(
                MetadataCandidate.source_file_id == source.id
            )
        ).all()
        best = merge_candidates(list(rows), DEFAULT_METADATA_CONFIG)
        overall = overall_confidence(best)
        missing = [f for f in MetadataField if f not in best]
        print(
            render_report_text(
                source.file_path.split("/")[-1],
                best,
                overall,
                missing,
                None,
            )
        )
    return 0


def cmd_metadata_review(
    sha256: str,
    *,
    approve: str | None,
    reject: str | None,
    value: str | None,
    note: str | None,
    reviewer: str,
    publish: bool,
) -> int:
    """List candidates, apply review actions, and optionally publish."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.metadata.processor import apply_review, publish_metadata

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        source = session.scalar(
            select(SourceFile).where(SourceFile.sha256.startswith(sha256))
        )
        if source is None:
            print(f"No source matching sha256 prefix {sha256!r}", file=sys.stderr)
            return 1

        if approve is None and reject is None and not publish:
            _print_candidates(session, source)
            return 0

        if approve:
            target, error = apply_review(
                session,
                source,
                approve,
                approve=True,
                value=value,
                note=note,
                reviewer=reviewer,
            )
            if error:
                print(f"approve failed: {error}", file=sys.stderr)
                return 1
            assert target is not None
            logger.info(
                "approved metadata {} field={} value={}",
                source.sha256[:12], approve, target.value,
            )
            print(f"approved {target.field.value}: {target.value}")
        if reject:
            target, error = apply_review(
                session,
                source,
                reject,
                reject=True,
                note=note,
                reviewer=reviewer,
            )
            if error:
                print(f"reject failed: {error}", file=sys.stderr)
                return 1
            assert target is not None
            logger.info("rejected metadata {} field={}", source.sha256[:12], reject)
            print(f"rejected {target.field.value}: {target.value}")
        if publish:
            result = publish_metadata(session, source, reviewer=reviewer)
            if result.errors:
                for err in result.errors:
                    print(f"publish error: {err}", file=sys.stderr)
                return 1
            logger.info(
                "published metadata {} book={} edition={}",
                source.sha256[:12], result.book_id, result.edition_id,
            )
            print(
                f"published book={result.book_id} edition={result.edition_id} "
                f"created_book={result.created_book} created_edition={result.created_edition} "
                f"fields={result.fields}"
            )
    return 0


def _print_candidates(session: Session, source: SourceFile) -> None:
    from sqlalchemy import select

    from knowledge_base.database.models.metadata import MetadataCandidate

    rows = session.scalars(
        select(MetadataCandidate).where(MetadataCandidate.source_file_id == source.id)
        .order_by(MetadataCandidate.field, MetadataCandidate.created_at)
    ).all()
    if not rows:
        message = (
            "no metadata candidates yet — run "
            "'knowledge-base metadata extract --sha256 <prefix>'"
        )
        print(message)
        return
    print(f"Candidates for {source.sha256[:12]} ({source.file_path.split('/')[-1]}):")
    for candidate in rows:
        flags = [
            candidate.confidence.value,
            candidate.source.value,
            candidate.status.value,
        ]
        if candidate.uncertain:
            flags.append("uncertain")
        print(
            f"  {candidate.field.value:<18s} {candidate.value!r:<60s} "
            f"[{', '.join(flags)}]{'  ' + candidate.evidence if candidate.evidence else ''}"
        )


def _find_book(session: Session, sha256: str) -> Any:
    """Published Book whose source file matches a sha256 prefix."""
    from sqlalchemy import select

    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.sources import SourceFile

    return session.scalar(
        select(Book)
        .join(SourceFile, Book.source_file_id == SourceFile.id)
        .where(SourceFile.sha256.startswith(sha256))
    )


def cmd_structure_detect(
    sha256: str | None,
    *,
    structure_all: bool = False,
    limit: int | None = None,
) -> int:
    """Detect book structure from extraction output (idempotent per book)."""
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.logging import logger
    from knowledge_base.pipeline.structure.processor import (
        detect_structure,
        detect_structure_all,
    )

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        if sha256:
            book = _find_book(session, sha256)
            if book is None:
                print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
                return 1
            results = [detect_structure(book, session=session, data_dir=settings.data_dir)]
        elif structure_all:
            results = detect_structure_all(session, settings=settings, limit=limit)
        else:
            print("Use --sha256 <prefix> or --all", file=sys.stderr)
            return 2

    for result in results:
        logger.info(
            "structure {} chapters={} sections={} subsections={} blocks={} flagged={}",
            result.sha256[:12], len(result.chapters), result.section_count,
            result.subsection_count, result.block_count, result.flagged_count,
        )
        print(
            f"{result.sha256[:12]:12s} pages={result.pages_with_text:<4d} "
            f"chapters={len(result.chapters):<3d} sections={result.section_count:<3d} "
            f"subsections={result.subsection_count:<3d} blocks={result.block_count:<4d} "
            f"flagged={result.flagged_count}  {result.error or result.report_path}"
        )
    return 0


def cmd_structure_show(sha256: str) -> int:
    """Print the detected structure of one book from the database."""
    from sqlalchemy import func, select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.enums import ContentStatus
    from knowledge_base.database.models.structure import (
        Chapter,
        ContentBlock,
        Page,
        Paragraph,
        Section,
        Subsection,
    )

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        book = _find_book(session, sha256)
        if book is None:
            print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
            return 1
        chapters = session.scalars(
            select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.number)
        ).all()
        sections = session.scalars(
            select(Section).where(Section.book_id == book.id).order_by(Section.number)
        ).all()
        subsections = session.scalars(
            select(Subsection).where(Subsection.book_id == book.id).order_by(Subsection.number)
        ).all()
        page_count = session.scalar(
            select(func.count()).select_from(Page).where(Page.book_id == book.id)
        ) or 0
        paragraph_count = session.scalar(
            select(func.count()).select_from(Paragraph).where(Paragraph.book_id == book.id)
        ) or 0
        flagged = session.scalars(
            select(ContentBlock)
            .where(ContentBlock.book_id == book.id, ContentBlock.status == ContentStatus.REVIEW)
            .order_by(ContentBlock.page_id, ContentBlock.sequence)
        ).all()

        print(f"Book: {book.title}  ({book.id})")
        print(f"Pages: {page_count}  paragraphs: {paragraph_count}")
        for chapter in chapters:
            print(f"  {chapter.number:>3d} {chapter.kind.value:<18s} {chapter.title}")
            for section in sections:
                if section.chapter_id == chapter.id:
                    print(f"        {section.number:>3d} section  {section.title}")
            for subsection in subsections:
                for section in sections:
                    if subsection.section_id == section.id and section.chapter_id == chapter.id:
                        label = f"{subsection.number:>3d} subsection  {subsection.title}"
                        print(f"              {label}")
        print(f"Flagged for review: {len(flagged)}")
        for block in flagged:
            text = block.original_text.replace("\n", " ")
            if len(text) > 60:
                text = text[:60] + "…"
            print(f"  p.{block.page_number} seq={block.sequence} {text}")
            if block.notes:
                print(f"    note: {block.notes}")
    return 0


def cmd_structure_review(
    sha256: str,
    *,
    list_blocks: bool = False,
    approve: str | None = None,
    reject: str | None = None,
    note: str | None = None,
    reviewer: str = "cli",
) -> int:
    """List blocks flagged for review and approve / reject them."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.enums import ContentStatus
    from knowledge_base.database.models.structure import ContentBlock, Page
    from knowledge_base.logging import logger

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    def _parse_key(key: str) -> tuple[int, int]:
        parts = key.split(":")
        if len(parts) != 2:
            raise ValueError("expected PAGE:SEQ, e.g. 3:12")
        return int(parts[0]), int(parts[1])

    with session_scope(factory) as session:
        book = _find_book(session, sha256)
        if book is None:
            print(f"No published book matching sha256 prefix {sha256!r}", file=sys.stderr)
            return 1

        flagged = session.scalars(
            select(ContentBlock)
            .where(ContentBlock.book_id == book.id, ContentBlock.status == ContentStatus.REVIEW)
            .order_by(ContentBlock.page_id, ContentBlock.sequence)
        ).all()
        if list_blocks or (approve is None and reject is None):
            if not flagged:
                print(f"No blocks flagged for review for {sha256[:12]}")
            else:
                print(f"Flagged blocks for {book.title} ({len(flagged)}):")
                for flagged_block in flagged:
                    text = flagged_block.original_text.replace("\n", " ")
                    if len(text) > 60:
                        text = text[:60] + "…"
                    print(f"  p.{flagged_block.page_number} seq={flagged_block.sequence}: {text}")
                    if flagged_block.notes:
                        print(f"      note: {flagged_block.notes}")
            if approve is None and reject is None:
                return 0

        try:
            target_key = approve or reject
            page_no, seq = _parse_key(target_key or "")
        except ValueError as exc:
            print(f"{exc}", file=sys.stderr)
            return 2

        target = session.scalar(
            select(ContentBlock)
            .join(Page, ContentBlock.page_id == Page.id)
            .where(
                ContentBlock.book_id == book.id,
                Page.page_number == page_no,
                ContentBlock.sequence == seq,
            )
        )
        if target is None:
            print(f"No block at p.{page_no} seq={seq}", file=sys.stderr)
            return 1

        if approve:
            target.status = ContentStatus.PUBLISHED
            action = "approved"
        else:
            target.status = ContentStatus.QUARANTINED
            action = "rejected"
        annotation = note or f"{action} by {reviewer}"
        target.notes = f"{target.notes + '; ' if target.notes else ''}{annotation}".strip()
        logger.info(
            "structure review {} p.{} seq={} -> {}",
            sha256[:12], page_no, seq, target.status.value,
        )
        print(f"{action} p.{page_no} seq={seq} ({target.original_text[:40]!r})")
    return 0


def _load_user_items(path: Path | None) -> list[tuple[str, str]] | None:
    if path is None:
        return None
    import json as _json

    if not path.is_file():
        raise ValueError(f"user metadata file not found: {path}")
    data = _json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [(str(k), str(v)) for k, v in data.items()]
    if isinstance(data, list):
        return [(str(d["field"]), str(d.get("value", ""))) for d in data]
    raise ValueError("user metadata json must be an object or a list of {field, value}")


def cmd_cite(
    sha256: str,
    *,
    limit: int = 20,
    as_json: bool = False,
) -> int:
    """Print DB-originated source citations for a source file's chunks."""
    from sqlalchemy import select

    from knowledge_base.citations import citation_from_db
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.database.models.structure import ContentChunk

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        stmt = (
            select(ContentChunk)
            .join(SourceFile, ContentChunk.source_file_id == SourceFile.id)
            .where(SourceFile.sha256.startswith(sha256))
            .order_by(ContentChunk.sequence)
            .limit(limit)
        )
        chunks = session.scalars(stmt).all()
        citations = [citation_from_db(c) for c in chunks]

    if as_json:
        print(json.dumps([c.to_dict() for c in citations], ensure_ascii=False, indent=2))
    else:
        if not citations:
            print(f"No content found for source sha256 '{sha256}'.")
            return 0
        for idx, citation in enumerate(citations, start=1):
            print(f"[{idx}] {citation.reference()}")
            print(f"    Source: {citation.source_sha256}")
            if citation.page is not None:
                print(f"    Page:   {citation.page}")
            if citation.chunk_id:
                print(f"    Chunk:  {citation.chunk_id}")
            if citation.content_id:
                print(f"    Content: {citation.content_id}")
    return 0


__all__ = [
    "cmd_env",
    "cmd_glob",
    "cmd_ingest",
    "cmd_inspect",
    "cmd_extract",
    "cmd_ocr",
    "cmd_metadata_extract",
    "cmd_metadata_show",
    "cmd_metadata_review",
    "cmd_normalize",
    "cmd_structure_detect",
    "cmd_structure_show",
    "cmd_structure_review",
    "cmd_chunk_run",
    "cmd_index_run",
    "cmd_embed_run",
    "cmd_search",
    "cmd_similar",
    "cmd_hybrid",
    "cmd_cite",
    "cmd_version",
]
