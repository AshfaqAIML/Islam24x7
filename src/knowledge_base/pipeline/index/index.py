"""Full-text search index pipeline stage.

Turns each published book's retrieval chunks into ``search_documents`` rows:
the normalized chunk text plus the book title (both language-flagged) become
the body of a PostgreSQL ``tsvector`` document, populated and kept in sync by
database triggers. Re-running the stage is idempotent — it replaces the book's
documents and its single ``INDEX`` job record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import JobStatus, JobType, Language
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.search import SearchDocument
from knowledge_base.database.models.structure import ContentChunk
from knowledge_base.logging import logger
from knowledge_base.pipeline.jobs import upsert_processing_job
from knowledge_base.pipeline.normalize.processor import book_language


@dataclass
class IndexResult:
    """Outcome of indexing one book's chunks as search documents."""

    sha256: str
    book_id: str
    source_file_id: str
    error: str | None = None
    report_path: Path | None = None
    language: Language = Language.OTHER
    chunk_count: int = 0
    document_count: int = 0


def _load_chunks(session: Session, book_id: str) -> list[ContentChunk]:
    return list(
        session.scalars(
            select(ContentChunk)
            .where(ContentChunk.book_id == book_id)
            .order_by(ContentChunk.sequence)
        )
    )


def index_book(
    book: Book,
    *,
    session: Session,
    data_dir: Path,
) -> IndexResult:
    """Index a published book's chunks as search documents (idempotent)."""
    source_file = book.source_file
    sha256 = source_file.sha256
    book_id = str(book.id)
    language = book_language(book)
    result = IndexResult(
        sha256=sha256,
        book_id=book_id,
        source_file_id=str(source_file.id),
        language=language,
    )

    chunks = _load_chunks(session, book_id)
    if not chunks:
        result.error = "book has no chunks; did the chunk stage run?"
        result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
        _write_report(result)
        _upsert_job(session, result)
        return result

    session.execute(
        delete(SearchDocument).where(
            SearchDocument.content_chunk_id.in_(
                select(ContentChunk.id).where(ContentChunk.book_id == book_id)
            )
        )
    )
    session.flush()

    for chunk in chunks:
        session.add(
            SearchDocument(
                content_chunk_id=chunk.id,
                document_type="chunk",
                language=language,
                title=book.title,
                body_text=chunk.text,
            )
        )
        result.document_count += 1
    result.chunk_count = len(chunks)
    result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
    _write_report(result)
    _upsert_job(session, result)
    return result


def index_all(
    session: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
) -> list[IndexResult]:
    """Index every published book (idempotent)."""
    if settings is None:
        settings = get_settings()
    books = session.scalars(select(Book).order_by(Book.created_at)).all()
    if limit is not None:
        books = books[:limit]
    results: list[IndexResult] = []
    for book in books:
        logger.info("index book={} {}", book.title, book.id)
        results.append(index_book(book, session=session, data_dir=settings.data_dir))
    return results


def _report_dir(data_dir: Path) -> Path:
    return data_dir.resolve() / "processed" / "index"


def _render_report(result: IndexResult) -> str:
    return (
        f"Search index for {result.sha256[:12]} (book {result.book_id[:8]})\n"
        f"Language: {result.language.value}\n"
        f"Chunks={result.chunk_count} documents={result.document_count}\n"
        + (f"Error: {result.error}\n" if result.error else "")
    )


def _write_report(result: IndexResult) -> None:
    assert result.report_path is not None
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    result.report_path.write_text(_render_report(result), encoding="utf-8")


def _upsert_job(session: Session, result: IndexResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.INDEX,
        status=status,
        manifest={
            "language": result.language.value,
            "chunk_count": result.chunk_count,
            "document_count": result.document_count,
            "report": result.report_path.name if result.report_path else None,
        },
        error=result.error,
    )


__all__ = ["IndexResult", "index_all", "index_book"]