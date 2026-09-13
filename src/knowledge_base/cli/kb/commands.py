"""``kb`` command implementations.

All functions accept parsed arguments and return an integer exit code.
Logic lives in ``knowledge_base.pipeline.*`` and ``knowledge_base.search.*``;
this module handles user-facing I/O, progress, and exit codes only.
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import replace as dataclasses_replace
from pathlib import Path
from typing import Any

from knowledge_base.cli.kb.progress import (
    Progress,
    cyan,
    dim,
    green,
    red,
    render_table,
    status_symbol,
    yellow,
)
from knowledge_base.config import get_settings

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

APP = "kb"


def _settings() -> Any:
    return get_settings()


def _err(msg: str) -> None:
    print(f"{APP}: error: {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"{APP}: {yellow('warning')}: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"{APP}: {msg}", file=sys.stderr)


def _dump_json(obj: object) -> int:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def cmd_inspect(path: Path, *, as_json: bool = False) -> int:
    """Classify a raw file: format, pages, text-layer, language hints."""
    if not path.exists():
        _err(f"file not found: {path}")
        return 1
    import pymupdf

    try:
        doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    except Exception as exc:
        info: dict[str, object] = {
            "path": str(path),
            "status": "corrupt",
            "error": str(exc),
        }
        if as_json:
            return _dump_json(info)
        _err(f"cannot open PDF: {exc}")
        return 1

    page_count = len(doc)
    meta = doc.metadata or {}
    pages_with_text = 0
    language_hints: dict[str, int] = {}
    for i in range(min(page_count, 8)):
        text = (doc.load_page(i).get_text("text") or "").strip()  # type: ignore[no-untyped-call]
        if text:
            pages_with_text += 1
            for ch in text:
                cp = ord(ch)
                if 0x0600 <= cp <= 0x06FF or 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
                    language_hints["ar"] = language_hints.get("ar", 0) + 1
                elif 0x0900 <= cp <= 0x097F:
                    language_hints["ur"] = language_hints.get("ur", 0) + 1
                elif cp < 0x0400:
                    language_hints["en"] = language_hints.get("en", 0) + 1

    if pages_with_text == 0:
        classification = "scanned"
    elif pages_with_text < page_count:
        classification = "mixed"
    else:
        classification = "text"

    top_lang = max(language_hints, key=lambda k: language_hints[k]) if language_hints else None

    doc.close()  # type: ignore[no-untyped-call]
    info = {
        "path": str(path),
        "status": "ok",
        "classification": classification,
        "page_count": page_count,
        "pages_with_text": pages_with_text,
        "language_hint": top_lang,
        "title": meta.get("title") or None,
        "author": meta.get("author") or None,
    }
    if as_json:
        return _dump_json(info)
    print(cyan("File inspection") + f" — {path.name}")
    print(
        render_table(
            [
                ["Classification", classification],
                ["Pages", str(page_count)],
                ["Text pages", str(pages_with_text)],
                ["Language hint", top_lang or "—"],
                ["Title", str(info["title"] or "—")],
                ["Author", str(info["author"] or "—")],
            ]
        )
    )
    return 0


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def cmd_import(
    paths: list[Path],
    *,
    category: str = "books",
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    """Import files or directories into the knowledge base."""
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    data_dir = settings.resolve().data_dir

    results: list[dict[str, Any]] = []
    with session_scope(factory) as session:
        for target in sorted(paths):
            if target.is_dir():
                files = sorted(f for f in target.rglob("*") if f.is_file())
                progress = Progress(len(files), label=target.name)
                for fp in files:
                    results.append(_import_one(session, fp, data_dir, category, dry_run))
                    progress.update(label=fp.name)
                progress.finish()
            elif target.is_file():
                results.append(_import_one(session, target, data_dir, category, dry_run))
            else:
                _warn(f"skipping (not a file or dir): {target}")

    if as_json:
        return _dump_json(results)

    registered = sum(1 for r in results if r["status"] == "registered")
    duplicates = sum(1 for r in results if r["status"] == "duplicate")
    quarantined = sum(1 for r in results if r["status"] == "quarantined")
    failed = sum(1 for r in results if r["status"] == "failed")
    for r in results:
        if r["status"] in ("quarantined", "failed"):
            _warn(f"{r['status']}: {r['path']} ({r['reason']})")
    _info(
        f"{green('done')}: {registered} registered, {duplicates} duplicates, "
        f"{quarantined} quarantined, {failed} failed"
    )
    return 0 if quarantined == 0 and failed == 0 else 1


def _import_one(
    session: Any, fp: Path, data_dir: Path, category: str, dry_run: bool
) -> dict[str, Any]:
    from knowledge_base.pipeline.ingest.ingest import ingest_file

    r = ingest_file(fp, session=session, data_dir=data_dir, category=category, dry_run=dry_run)
    return {"path": str(fp), "sha256": r.sha256, "status": r.status, "reason": r.reason}


# ---------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------


def cmd_process(
    *,
    sha256: str | None = None,
    source_path: Path | None = None,
    pending: bool = False,
    all_sources: bool = False,
    limit: int | None = None,
    force: bool = False,
    auto_review: bool = True,
    continue_on_error: bool = False,
    start_from: str | None = None,
    stop_at: str | None = None,
    ocr_engine: str | None = None,
    embed_provider: str | None = None,
    dry_run: bool = False,
    as_json: bool = False,
) -> int:
    """Run the full processing pipeline for one or more sources."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.pipeline.orchestrator import (
        run_pipeline,
        run_pipeline_all,
        run_pipeline_from_file,
    )

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    data_dir = settings.resolve().data_dir

    # Build kwargs for run_pipeline calls
    run_kwargs: dict[str, Any] = dict(
        data_dir=data_dir,
        force=force,
        auto_review=auto_review,
        continue_on_error=continue_on_error,
        start_from=start_from,
        stop_at=stop_at,
    )
    if ocr_engine:
        from knowledge_base.pipeline.ocr.config import OcrConfig
        from knowledge_base.pipeline.ocr.engines import build_engine

        ocr_cfg = OcrConfig(engine=ocr_engine)
        run_kwargs["ocr_engine"] = build_engine(ocr_engine, ocr_cfg)
        run_kwargs["ocr_config"] = ocr_cfg
    if embed_provider:
        from knowledge_base.pipeline.embed.config import EmbedConfig
        from knowledge_base.pipeline.embed.provider import build_provider

        embed_cfg = EmbedConfig()
        run_kwargs["embed_provider"] = build_provider(embed_provider, embed_cfg)
        run_kwargs["embed_config"] = embed_cfg

    with session_scope(factory) as session:
        if source_path:
            _info(f"importing and processing {source_path.name}")
            if dry_run:
                _info("dry run: would import and process")
                return 0
            _ing, result = run_pipeline_from_file(
                session, source_path, category="books", **run_kwargs
            )
            if result is None:
                _err(f"ingestion failed: {_ing.reason or _ing.status}")
                return 1
            results_list = [result]
        elif sha256:
            source = session.scalar(select(SourceFile).where(SourceFile.sha256.startswith(sha256)))
            if source is None:
                _err(f"no source matching sha256 prefix {sha256!r}")
                return 1
            if dry_run:
                _info(f"dry run: would process source {source.sha256[:12]}")
                return 0
            results_list = [run_pipeline(session, source, **run_kwargs)]
        elif pending:
            results_list = _run_pending(session, run_kwargs, limit, dry_run)
        else:
            if dry_run:
                _info("dry run: would process all sources")
                return 0
            results_list = run_pipeline_all(session, **run_kwargs, limit=limit)

    if as_json:
        return _dump_json([r.to_dict() for r in results_list])
    return _print_pipeline_results(results_list)


def _run_pending(
    session: Any, run_kwargs: dict[str, Any], limit: int | None, dry_run: bool
) -> list[Any]:
    from sqlalchemy import select

    from knowledge_base.database.enums import JobStatus
    from knowledge_base.database.models.sources import ProcessingJob, SourceFile
    from knowledge_base.pipeline.orchestrator import run_pipeline

    sources = session.scalars(select(SourceFile).order_by(SourceFile.created_at)).all()
    pending_sources = []
    for src in sources:
        jobs = session.scalars(
            select(ProcessingJob).where(ProcessingJob.source_file_id == src.id)
        ).all()
        if not jobs or any(j.status in (JobStatus.FAILED, JobStatus.PENDING) for j in jobs):
            pending_sources.append(src)
    if limit:
        pending_sources = pending_sources[:limit]
    if dry_run:
        _info(f"dry run: {len(pending_sources)} source(s) would be processed")
        return []
    _info(f"found {len(pending_sources)} source(s) needing processing")
    results = []
    for src in pending_sources:
        results.append(run_pipeline(session, src, **run_kwargs))
    return results


def _print_pipeline_results(results: list[Any]) -> int:
    failed = False
    for result in results:
        stages = ", ".join(f"{s.name}={s.status}" for s in result.stages)
        overall = status_symbol(result.overall)
        print(f"{result.sha256[:12]}  {overall}  {dim(stages)}")
        if result.overall == "FAILED":
            for s in result.stages:
                if s.status == "FAILED":
                    _err(f"  {s.name}: {s.error}")
            failed = True
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def cmd_validate(
    *,
    sha256: str | None = None,
    book_id: str | None = None,
    as_json: bool = False,
) -> int:
    """Validate knowledge-base integrity: chains, invariants, orphans."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.sources import SourceFile

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        issues: list[dict[str, Any]] = []
        if sha256:
            sf = session.scalar(select(SourceFile).where(SourceFile.sha256.startswith(sha256)))
            if sf is None:
                _err(f"no source matching {sha256!r}")
                return 1
            book = session.scalar(select(Book).where(Book.source_file_id == sf.id))
            if book is None:
                issues.append({"severity": "warning", "message": "source has no published book"})
                return _validate_report(issues, as_json)
            _validate_book(session, book, issues)
        elif book_id:
            book = session.scalar(select(Book).where(Book.id == uuid.UUID(book_id)))
            if book is None:
                _err(f"no book matching id {book_id!r}")
                return 1
            _validate_book(session, book, issues)
        else:
            books = session.scalars(select(Book).order_by(Book.created_at)).all()
            for book in books:
                _validate_book(session, book, issues)

        if not issues:
            issues.append({"severity": "ok", "message": "no issues found"})

    return _validate_report(issues, as_json)


def _validate_book(session: Any, book: Any, issues: list[dict[str, Any]]) -> None:
    from sqlalchemy import func, select

    from knowledge_base.database.models.embeddings import Embedding
    from knowledge_base.database.models.normalization import NormalizedText
    from knowledge_base.database.models.search import SearchDocument
    from knowledge_base.database.models.structure import ContentBlock, ContentChunk

    book_id = str(book.id)
    block_count = (
        session.scalar(
            select(func.count()).select_from(ContentBlock).where(ContentBlock.book_id == book_id)
        )
        or 0
    )
    chunk_count = (
        session.scalar(
            select(func.count()).select_from(ContentChunk).where(ContentChunk.book_id == book_id)
        )
        or 0
    )
    search_doc_count = (
        session.scalar(
            select(func.count())
            .select_from(SearchDocument)
            .join(ContentChunk, SearchDocument.content_chunk_id == ContentChunk.id)
            .where(ContentChunk.book_id == book_id)
        )
        or 0
    )
    embedding_count = (
        session.scalar(
            select(func.count())
            .select_from(Embedding)
            .join(ContentChunk, Embedding.content_chunk_id == ContentChunk.id)
            .where(ContentChunk.book_id == book_id)
        )
        or 0
    )
    normalized_count = (
        session.scalar(
            select(func.count())
            .select_from(NormalizedText)
            .where(NormalizedText.book_id == book_id)
        )
        or 0
    )
    if block_count == 0:
        issues.append({"severity": "critical", "book": book.title, "message": "no content blocks"})
    if chunk_count == 0:
        issues.append({"severity": "critical", "book": book.title, "message": "no chunks"})
    if block_count > 0 and search_doc_count == 0:
        issues.append(
            {
                "severity": "warning",
                "book": book.title,
                "message": f"blocks={block_count} but search_documents=0",
            }
        )
    if chunk_count > 0 and embedding_count == 0:
        issues.append(
            {
                "severity": "warning",
                "book": book.title,
                "message": f"chunks={chunk_count} but embeddings=0",
            }
        )
    if normalized_count == 0 and block_count > 0:
        issues.append(
            {
                "severity": "info",
                "book": book.title,
                "message": f"no normalized_texts for {block_count} blocks",
            }
        )

    # orphaned embeddings (rows whose chunk was deleted)
    orphan_emb = (
        session.scalar(
            select(func.count())
            .select_from(Embedding)
            .join(ContentChunk, Embedding.content_chunk_id == ContentChunk.id, isouter=True)
            .where(ContentChunk.id.is_(None))
        )
        or 0
    )
    if orphan_emb > 0:
        issues.append(
            {
                "severity": "warning",
                "book": book.title,
                "message": f"{orphan_emb} orphaned embeddings",
            }
        )


def _validate_report(issues: list[dict[str, Any]], as_json: bool) -> int:
    if as_json:
        return _dump_json(issues)
    criticals = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos = [i for i in issues if i["severity"] == "info"]
    oks = [i for i in issues if i["severity"] == "ok"]
    if oks:
        print(green("OK") + " — " + oks[0]["message"])
        return 0
    for i in criticals:
        print(red("CRITICAL") + f" [{i.get('book', '—')}] {i['message']}")
    for i in warnings:
        print(yellow("WARNING") + f" [{i.get('book', '—')}] {i['message']}")
    for i in infos:
        print(f"  info [{i.get('book', '—')}] {i['message']}")
    return 1 if criticals else 0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


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
    """Full-text search across the knowledge base."""

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.search.engine import SearchParams, search

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    params = SearchParams(
        query=query,
        domains=domains or ("content", "book", "chapter", "section", "quran", "hadith"),
        all_terms=all_terms,
        language=language,
        category=category,
        source=source,
        author=author,
        limit=limit,
    )
    with session_scope(factory) as session:
        hits = search(session, params)

    if as_json:
        from dataclasses import asdict

        return _dump_json([asdict(h) for h in hits])

    if not hits:
        _info("no results found")
        return 0

    rows: list[list[str]] = []
    for i, h in enumerate(hits, 1):
        snippet = (h.snippet or h.matched_text)[:120].replace("\n", " ")
        citation = h.citation or ""
        chapter_sec = f"{h.chapter or ''}"
        if h.section:
            chapter_sec += f" / {h.section}"
        chapter_sec = chapter_sec.strip(" /") or "—"
        rows.append(
            [
                f"{i}.",
                cyan(h.domain),
                (h.title or "—")[:40],
                chapter_sec[:30],
                snippet[:80],
                citation[:20],
            ]
        )
    header = ["#", "domain", "book", "chapter", "snippet", "citation"]
    print(render_table([header] + rows))
    return 0


# ---------------------------------------------------------------------------
# embed
# ---------------------------------------------------------------------------


def cmd_embed(
    *,
    sha256: str | None = None,
    all_sources: bool = False,
    limit: int | None = None,
    provider_name: str | None = None,
    model: str | None = None,
    model_version: str | None = None,
    dimensions: int | None = None,
    batch_size: int | None = None,
    as_json: bool = False,
) -> int:
    """Generate chunk embeddings for vector search."""

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.pipeline.embed.config import EmbedConfig
    from knowledge_base.pipeline.embed.processor import embed_book

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    cfg = EmbedConfig()
    if provider_name:
        cfg = dataclasses_replace(cfg, provider_name=provider_name)
    if model:
        cfg = dataclasses_replace(cfg, model_name=model)
    if model_version:
        cfg = dataclasses_replace(cfg, model_version=model_version)
    if dimensions:
        cfg = dataclasses_replace(cfg, dimensions=dimensions)
    if batch_size:
        cfg = dataclasses_replace(cfg, batch_size=batch_size)

    from knowledge_base.pipeline.embed.provider import build_provider

    provider = build_provider(cfg.provider_name, cfg)

    with session_scope(factory) as session:
        books = _resolve_books(session, sha256, all_sources, limit)
        if not books:
            _info("no books to embed")
            return 0
        progress = Progress(len(books), label="embed")
        results: list[Any] = []
        for book in books:
            r = embed_book(
                book,
                session=session,
                data_dir=settings.resolve().data_dir,
                provider=provider,
                config=cfg,
            )
            results.append(r)
            progress.update(label=book.title[:30] if book.title else book.id.hex[:12])
        progress.finish()

    if as_json:
        return _dump_json(
            [
                {
                    "book_id": r.book_id,
                    "embedded": r.embedded_count,
                    "updated": r.updated_count,
                    "reused": r.reused_count,
                }
                for r in results
            ]
        )
    for r in results:
        msg = f"{r.book_id[:12]}  embedded={r.embedded_count} "
        msg += f"updated={r.updated_count} reused={r.reused_count}"
        _info(msg)
    return 0


# ---------------------------------------------------------------------------
# reindex
# ---------------------------------------------------------------------------


def cmd_reindex(
    *,
    sha256: str | None = None,
    all_sources: bool = False,
    limit: int | None = None,
    as_json: bool = False,
) -> int:
    """Rebuild full-text search documents for published books."""

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.pipeline.index.index import index_book

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        books = _resolve_books(session, sha256, all_sources, limit)
        if not books:
            _info("no books to index")
            return 0
        progress = Progress(len(books), label="reindex")
        results: list[Any] = []
        for book in books:
            r = index_book(book, session=session, data_dir=settings.resolve().data_dir)
            results.append(r)
            progress.update(label=book.title[:30] if book.title else book.id.hex[:12])
        progress.finish()

    if as_json:
        return _dump_json([{"book_id": r.book_id, "documents": r.document_count} for r in results])
    for r in results:
        _info(f"{r.book_id[:12]}  documents={r.document_count}")
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(*, as_json: bool = False) -> int:
    """Show a dashboard of the knowledge base."""
    from sqlalchemy import func, select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.enums import JobStatus
    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.embeddings import Embedding
    from knowledge_base.database.models.hadith import Hadith
    from knowledge_base.database.models.quran import Ayah, Translation
    from knowledge_base.database.models.search import SearchDocument
    from knowledge_base.database.models.sources import ProcessingJob, SourceFile
    from knowledge_base.database.models.structure import ContentChunk

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        sources = session.scalar(select(func.count()).select_from(SourceFile)) or 0
        books = session.scalar(select(func.count()).select_from(Book)) or 0
        chunks = session.scalar(select(func.count()).select_from(ContentChunk)) or 0
        embeddings = session.scalar(select(func.count()).select_from(Embedding)) or 0
        search_docs = session.scalar(select(func.count()).select_from(SearchDocument)) or 0
        quran_ayahs = session.scalar(select(func.count()).select_from(Ayah)) or 0
        quran_translations = session.scalar(select(func.count()).select_from(Translation)) or 0
        hadith = session.scalar(select(func.count()).select_from(Hadith)) or 0

        # Jobs by status
        job_rows = session.execute(
            select(ProcessingJob.status, func.count()).group_by(ProcessingJob.status)
        ).all()

        def _key(row: Any) -> str:
            value = row[0]
            return str(value.value if hasattr(value, "value") else value)

        jobs_by_status = {_key(row): row[1] for row in job_rows}

        # Jobs by type (succeeded)
        job_type_rows = session.execute(
            select(ProcessingJob.job_type, func.count())
            .where(ProcessingJob.status == JobStatus.SUCCEEDED)
            .group_by(ProcessingJob.job_type)
        ).all()
        completed_by_type = {_key(row): row[1] for row in job_type_rows}

    dashboard = {
        "sources": sources,
        "books": books,
        "chunks": chunks,
        "embeddings": embeddings,
        "search_documents": search_docs,
        "quran_ayahs": quran_ayahs,
        "quran_translations": quran_translations,
        "hadith": hadith,
        "jobs_by_status": jobs_by_status,
        "completed_by_type": completed_by_type,
    }

    if as_json:
        return _dump_json(dashboard)

    print(cyan("Knowledge Base Dashboard"))
    print(
        render_table(
            [
                ["Sources", str(sources)],
                ["Published books", str(books)],
                ["Content chunks", str(chunks)],
                ["Embeddings", str(embeddings)],
                ["Search documents", str(search_docs)],
                ["Quran ayahs", str(quran_ayahs)],
                ["Quran translations", str(quran_translations)],
                ["Hadith records", str(hadith)],
            ]
        )
    )
    if jobs_by_status:
        print()
        print(dim("Job status"))
        for status, count in sorted(jobs_by_status.items()):
            print(f"  {status_symbol(status):<30s} {count}")
    if completed_by_type:
        print()
        print(dim("Completed by type"))
        for jtype, count in sorted(completed_by_type.items()):
            print(f"  {jtype:<30s} {count}")
    return 0


# ---------------------------------------------------------------------------
# retry
# ---------------------------------------------------------------------------


def cmd_retry(
    *,
    sha256: str | None = None,
    pending_only: bool = True,
    all_sources: bool = False,
    as_json: bool = False,
) -> int:
    """Re-run failed/pending stages for sources that need it."""
    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.enums import JobStatus
    from knowledge_base.database.models.sources import ProcessingJob, SourceFile
    from knowledge_base.pipeline.orchestrator import run_pipeline

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    data_dir = settings.resolve().data_dir

    with session_scope(factory) as session:
        if sha256:
            sf = session.scalar(select(SourceFile).where(SourceFile.sha256.startswith(sha256)))
            if sf is None:
                _err(f"no source matching {sha256!r}")
                return 1
            sources = [sf]
        else:
            all_sf = session.scalars(select(SourceFile).order_by(SourceFile.created_at)).all()
            sources = []
            for src in all_sf:
                jobs = session.scalars(
                    select(ProcessingJob).where(ProcessingJob.source_file_id == src.id)
                ).all()
                if not jobs or any(j.status in (JobStatus.FAILED, JobStatus.PENDING) for j in jobs):
                    sources.append(src)

    if not sources:
        _info("nothing to retry")
        return 0

    _info(f"retrying {len(sources)} source(s)")
    with session_scope(factory) as session:
        results = []
        for src in sources:
            r = run_pipeline(session, src, data_dir=data_dir)
            results.append(r)

    if as_json:
        return _dump_json([r.to_dict() for r in results])
    return _print_pipeline_results(results)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def cmd_stats(*, as_json: bool = False) -> int:
    """Show aggregate statistics across the knowledge base."""
    from sqlalchemy import func, select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.books import Book, Category
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.database.models.structure import ContentChunk

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        # by category
        cat_rows = session.execute(
            select(Category.code, func.count())
            .join(Book, Book.category_id == Category.id, isouter=True)
            .group_by(Category.code)
        ).all()
        by_category = {str(row[0] or "uncategorized"): row[1] for row in cat_rows}

        # chunk stats
        avg_tokens = session.scalar(select(func.avg(ContentChunk.token_count))) or 0
        total_tokens = session.scalar(select(func.sum(ContentChunk.token_count))) or 0
        avg_pages_per_chunk = (
            session.scalar(select(func.avg(ContentChunk.page_end - ContentChunk.page_start + 1)))
            or 0
        )

        # source formats
        fmt_rows = session.execute(
            select(SourceFile.format, func.count()).group_by(SourceFile.format)
        ).all()

        def _fmt_key(row: Any) -> str:
            value = row[0]
            return str(value.value if hasattr(value, "value") else value)

        by_format = {_fmt_key(row): row[1] for row in fmt_rows}

    stats = {
        "by_category": by_category,
        "by_format": by_format,
        "avg_tokens_per_chunk": round(float(avg_tokens), 1),
        "total_tokens": int(total_tokens),
        "avg_pages_per_chunk": round(float(avg_pages_per_chunk), 1),
    }
    if as_json:
        return _dump_json(stats)

    print(cyan("Aggregate Statistics"))
    if by_category:
        print(dim("Books by category"))
        for cat, count in sorted(by_category.items()):
            print(f"  {cat:<25s} {count}")
    if by_format:
        print(dim("Sources by format"))
        for fmt, count in sorted(by_format.items()):
            print(f"  {fmt:<25s} {count}")
    print()
    print(
        render_table(
            [
                ["Avg tokens/chunk", f"{avg_tokens:.1f}"],
                ["Total tokens", f"{int(total_tokens):,}"],
                ["Avg pages/chunk", f"{avg_pages_per_chunk:.1f}"],
            ]
        )
    )
    return 0


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def cmd_export(
    *,
    sha256: str | None = None,
    book_id: str | None = None,
    all_sources: bool = False,
    limit: int | None = None,
    out_dir: Path = Path("data/exports"),
    fmt: str = "json",
) -> int:
    """Export book metadata and chunks to a file."""

    from sqlalchemy import select

    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.database.models.structure import ContentChunk

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)

    with session_scope(factory) as session:
        books = _resolve_books(session, sha256, all_sources, limit)
        if not books:
            _info("no books to export")
            return 0
        out_dir.mkdir(parents=True, exist_ok=True)
        exported = 0
        for book in books:
            chunks = session.scalars(
                select(ContentChunk)
                .where(ContentChunk.book_id == book.id)
                .order_by(ContentChunk.sequence)
            ).all()
            chunk_list = [
                {
                    "chunk_id": c.chunk_id,
                    "sequence": c.sequence,
                    "text": c.text,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "token_count": c.token_count,
                }
                for c in chunks
            ]
            payload = {
                "book_id": str(book.id),
                "title": book.title,
                "chunks": chunk_list,
            }
            stem = book.title.replace(" ", "_")[:60] if book.title else book.id.hex[:12]
            target = out_dir / f"{stem}.{fmt}"
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            _info(f"exported {target}")
            exported += 1
    _info(f"{exported} book(s) exported to {out_dir}/")
    return 0


# ---------------------------------------------------------------------------
# ask
# ---------------------------------------------------------------------------


def cmd_ask(
    question: str,
    *,
    language: str | None = None,
    category: str | None = None,
    source: str | None = None,
    author: str | None = None,
    k: int | None = None,
    as_json: bool = False,
) -> int:
    """Answer a question grounded in the knowledge base."""
    from knowledge_base.database import create_app_engine, make_session_factory, session_scope
    from knowledge_base.rag.service import RagService

    settings = _settings()
    engine = create_app_engine(settings.database_url)
    factory = make_session_factory(engine)
    svc = RagService(settings=settings)

    with session_scope(factory) as session:
        ans = svc.answer(
            session,
            question,
            language=language,
            category=category,
            source=source,
            author=author,
            k=k,
        )

    if as_json:
        from dataclasses import asdict

        return _dump_json(asdict(ans))

    badge = green("GROUNDED") if ans.grounded else yellow("UNGROUNDED")
    timing = f"{ans.retrieval_ms}ms retrieval + {ans.generation_ms}ms generation"
    print(f"{cyan('Answer')} — {badge}  {dim(timing)}")
    print()
    print(ans.answer or "(no answer)")
    if ans.sources:
        print()
        print(cyan(f"Sources ({len(ans.sources)})"))
        for i, src in enumerate(ans.sources, 1):
            print(f"  [{i}] {src.reference}  {dim(f'score={src.score:.3f}')}")
    if ans.ground_notes:
        print()
        print(dim("Notes: " + "; ".join(ans.ground_notes)))
    return 0


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _resolve_books(
    session: Any, sha256: str | None, all_sources: bool, limit: int | None
) -> list[Any]:
    from sqlalchemy import select

    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.sources import SourceFile

    if sha256:
        sf = session.scalar(select(SourceFile).where(SourceFile.sha256.startswith(sha256)))
        if sf is None:
            _err(f"no source matching {sha256!r}")
            return []
        book = session.scalar(select(Book).where(Book.source_file_id == sf.id))
        if book is None:
            _err("source has no published book")
            return []
        return [book]
    if all_sources:
        books = session.scalars(select(Book).order_by(Book.created_at)).all()
        return list(books[:limit] if limit else books)
    # default: all
    books = session.scalars(select(Book).order_by(Book.created_at)).all()
    return list(books[:limit] if limit else books)


__all__ = [
    "cmd_ask",
    "cmd_embed",
    "cmd_export",
    "cmd_import",
    "cmd_inspect",
    "cmd_process",
    "cmd_reindex",
    "cmd_retry",
    "cmd_search",
    "cmd_status",
    "cmd_stats",
    "cmd_validate",
]
