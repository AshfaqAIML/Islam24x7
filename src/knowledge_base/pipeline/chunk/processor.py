"""Chunk pipeline stage: materialize structure-aware chunks for a book.

Reads the published book's ``PARAGRAPH`` content blocks plus their
search-normalized variants, groups them into retrieval chunks (see
:mod:`knowledge_base.pipeline.chunk.chunker`), and rewrites the book's rows in
``content_chunks`` idempotently. The original text is never modified.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import BlockType, JobStatus, JobType, Language
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.normalization import NormalizedText
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Page,
    Section,
)
from knowledge_base.logging import logger
from knowledge_base.pipeline.chunk.chunker import (
    ParagraphUnit,
    build_chunks,
)
from knowledge_base.pipeline.chunk.config import ChunkConfig, estimate_tokens
from knowledge_base.pipeline.jobs import upsert_processing_job
from knowledge_base.pipeline.normalize.processor import book_language


@dataclass
class ChunkResult:
    """Outcome of chunking one book."""

    sha256: str
    book_id: str
    source_file_id: str
    error: str | None = None
    report_path: Path | None = None
    language: Language = Language.OTHER
    config: ChunkConfig = field(default_factory=ChunkConfig)
    chunk_count: int = 0
    paragraph_count: int = 0
    token_total: int = 0
    page_start: int | None = None
    page_end: int | None = None


def _load_paragraphs(
    session: Session, book_id: str
) -> list[tuple[ContentBlock, int | None, int | None, int | None]]:
    """(block, page_number, chapter_no, section_no) in book order."""
    rows = session.execute(
        select(ContentBlock, Page.page_number, Chapter.number, Section.number)
        .where(
            ContentBlock.book_id == book_id,
            ContentBlock.block_type == BlockType.PARAGRAPH,
        )
        .join(Page, ContentBlock.page_id == Page.id)
        .join(Chapter, ContentBlock.chapter_id == Chapter.id, isouter=True)
        .join(Section, ContentBlock.section_id == Section.id, isouter=True)
        .order_by(Page.page_number, ContentBlock.sequence)
    ).all()
    return [(block, page, chapter_no, section_no) for block, page, chapter_no, section_no in rows]


def _load_normalized(session: Session, book_id: str) -> dict[str, NormalizedText]:
    rows = session.scalars(
        select(NormalizedText).where(NormalizedText.book_id == book_id)
    ).all()
    return {str(r.content_block_id): r for r in rows}


def _id_maps(
    session: Session, book_id: str
) -> tuple[dict[int, uuid.UUID], dict[int, uuid.UUID]]:
    chapters = session.scalars(select(Chapter).where(Chapter.book_id == book_id)).all()
    sections = session.scalars(select(Section).where(Section.book_id == book_id)).all()
    chapter_ids = {c.number: c.id for c in chapters}
    section_ids = {s.number: s.id for s in sections}
    return chapter_ids, section_ids


def _render_report(result: ChunkResult) -> str:
    return (
        f"Chunking for {result.sha256[:12]} (book {result.book_id[:8]})\n"
        f"Language: {result.language.value}  "
        f"max_tokens={result.config.max_tokens} overlap={result.config.overlap_tokens}\n"
        f"Paragraphs={result.paragraph_count} chunks={result.chunk_count} "
        f"tokens={result.token_total}\n"
        f"Pages: {result.page_start}..{result.page_end}\n"
        + (f"Error: {result.error}\n" if result.error else "")
    )


def chunk_book(
    book: Book,
    *,
    session: Session,
    data_dir: Path,
    config: ChunkConfig | None = None,
) -> ChunkResult:
    """Materialize structure-aware chunks for the book (idempotent)."""
    if config is None:
        config = ChunkConfig()
    source_file = book.source_file
    sha256 = source_file.sha256
    book_id = str(book.id)
    result = ChunkResult(
        sha256=sha256,
        book_id=book_id,
        source_file_id=str(source_file.id),
        config=config,
        language=book_language(book),
    )

    paragraphs = _load_paragraphs(session, book_id)
    if not paragraphs:
        result.error = "book has no PARAGRAPH blocks; did structure detection run?"
        result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
        _write_report(result)
        _upsert_job(session, result)
        return result

    normalized = _load_normalized(session, book_id)
    chapter_ids, section_ids = _id_maps(session, book_id)

    units: list[ParagraphUnit] = []
    for block, page, chapter_no, section_no in paragraphs:
        norm = normalized.get(str(block.id))
        text = norm.normalized_text if norm is not None else block.original_text
        tokens = estimate_tokens(text, result.language)
        units.append(
            ParagraphUnit(
                block_id=str(block.id),
                chapter_no=chapter_no,
                section_no=section_no,
                page=page,
                sequence=block.sequence,
                text=text,
                tokens=tokens,
            )
        )

    chunks = build_chunks(
        units, source_sha=sha256, language=result.language, config=config
    )

    session.execute(delete(ContentChunk).where(ContentChunk.book_id == book_id))
    session.flush()

    for chunk in chunks:
        block_ids = chunk.block_ids
        is_normalized = all(
            normalized.get(block_id) is not None for block_id in block_ids
        )
        session.add(
            ContentChunk(
                chunk_id=chunk.chunk_id,
                book_id=book_id,
                content_block_id=block_ids[0],
                source_file_id=source_file.id,
                chapter_id=(
                    chapter_ids.get(chunk.chapter_no)
                    if chunk.chapter_no is not None
                    else None
                ),
                section_id=(
                    section_ids.get(chunk.section_no)
                    if chunk.section_no is not None
                    else None
                ),
                language=result.language,
                token_count=chunk.token_count,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                sequence=chunk.chunk_index,
                text=chunk.text,
                is_normalized=is_normalized,
                metadata_={
                    "chapter_no": chunk.chapter_no,
                    "section_no": chunk.section_no,
                    "block_ids": block_ids,
                },
            )
        )
        result.chunk_count += 1
        result.token_total += chunk.token_count
        pages = [p for p in (chunk.page_start, chunk.page_end) if p is not None]
        if pages:
            if result.page_start is None or min(pages) < result.page_start:
                result.page_start = min(pages)
            if result.page_end is None or max(pages) > result.page_end:
                result.page_end = max(pages)
    result.paragraph_count = len(units)
    result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
    _write_report(result)
    _upsert_job(session, result)
    return result


def chunk_all(
    session: Session,
    *,
    settings: Settings | None = None,
    config: ChunkConfig | None = None,
    limit: int | None = None,
) -> list[ChunkResult]:
    """Chunk every published book (idempotent)."""
    if settings is None:
        settings = get_settings()
    books = session.scalars(select(Book).order_by(Book.created_at)).all()
    if limit is not None:
        books = books[:limit]
    results: list[ChunkResult] = []
    for book in books:
        logger.info("chunk book={} {}", book.title, book.id)
        results.append(
            chunk_book(book, session=session, data_dir=settings.data_dir, config=config)
        )
    return results


def _report_dir(data_dir: Path) -> Path:
    return data_dir.resolve() / "processed" / "chunk"


def _write_report(result: ChunkResult) -> None:
    assert result.report_path is not None
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    result.report_path.write_text(_render_report(result), encoding="utf-8")


def _upsert_job(session: Session, result: ChunkResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.CHUNK,
        status=status,
        manifest={
            "language": result.language.value,
            "max_tokens": result.config.max_tokens,
            "overlap_tokens": result.config.overlap_tokens,
            "chunk_count": result.chunk_count,
            "paragraph_count": result.paragraph_count,
            "token_total": result.token_total,
            "page_start": result.page_start,
            "page_end": result.page_end,
            "report": result.report_path.name if result.report_path else None,
        },
        error=result.error,
    )


__all__ = ["ChunkResult", "chunk_all", "chunk_book"]