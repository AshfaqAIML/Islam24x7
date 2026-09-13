"""Tests for the structure-aware chunking system.

Two layers: pure unit tests for the token estimator and the grouping rules
(paragraphs never split, no section/chapter bleed, overlap, determinism), then
DB end-to-end tests proving every provenance field a chunk must carry
(book/chapter/section/page/source/content id, language, token count, metadata)
and that re-running is idempotent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import BlockType, JobStatus, JobType, Language, SourceFormat
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Page,
    Section,
)
from knowledge_base.pipeline.chunk.chunker import (
    ParagraphUnit,
    build_chunks,
    make_chunk_id,
)
from knowledge_base.pipeline.chunk.config import ChunkConfig, estimate_tokens
from knowledge_base.pipeline.chunk.processor import chunk_book


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ unit tests


def _u(
    block_id: str,
    chapter: int | None,
    section: int | None,
    page: int | None,
    text: str,
    tokens: int,
) -> ParagraphUnit:
    return ParagraphUnit(
        block_id=block_id,
        chapter_no=chapter,
        section_no=section,
        page=page,
        sequence=0,
        text=text,
        tokens=tokens,
    )


EN = Language.ENGLISH


def test_estimate_tokens_is_script_aware() -> None:
    assert estimate_tokens("abcd", Language.ENGLISH) == 1
    assert estimate_tokens("abcde", Language.ENGLISH) == 2
    assert estimate_tokens("الاتحاد", Language.ARABIC) == 3  # 7 chars / 3
    assert estimate_tokens("کتاب", Language.URDU) == 2  # 5 chars / 3
    assert estimate_tokens("", Language.ENGLISH) == 1  # never 0


def test_make_chunk_id_deterministic_and_positional() -> None:
    a = make_chunk_id("sha", 1, 1, 2, 3)
    assert a == make_chunk_id("sha", 1, 1, 2, 3)  # stable
    assert a != make_chunk_id("sha", 1, 1, 2, 4)  # index matters
    assert a != make_chunk_id("sha", 1, 2, 2, 3)  # section matters
    assert len(a) == 64


def test_never_splits_paragraph_and_respects_sections() -> None:
    units = [
        _u("p1", 1, 1, 1, "AA", 4),
        _u("p2", 1, 1, 1, "BB", 4),
        _u("p3", 1, 2, 1, "CC", 4),
        _u("p4", 1, 2, 3, "oversized" * 40, 500),
        _u("p5", 1, 2, 4, "DD", 4),
    ]
    chunks = build_chunks(
        units, source_sha="sha", language=EN, config=ChunkConfig(max_tokens=20, overlap_tokens=5)
    )

    assert [c.block_ids for c in chunks] == [
        ["p1", "p2"], ["p3"], ["p4"], ["p5"],
    ]
    # no overlap bleeds across the section boundary
    assert chunks[1].block_ids == ["p3"]
    # the oversized paragraph stays atomic (never split)
    assert chunks[2].block_ids == ["p4"]
    assert chunks[2].text == "oversized" * 40
    # page provenance per chunk
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 1)
    assert (chunks[3].page_start, chunks[3].page_end) == (4, 4)


def test_overlap_repeats_whole_paragraphs() -> None:
    units = [
        _u("p1", 1, 1, 1, "AA", 5),
        _u("p2", 1, 1, 1, "BB", 5),
        _u("p3", 1, 1, 2, "CC", 5),
        _u("p4", 1, 1, 2, "DD", 5),
    ]
    chunks = build_chunks(
        units, source_sha="sha", language=EN, config=ChunkConfig(max_tokens=16, overlap_tokens=6)
    )
    assert [c.block_ids for c in chunks] == [
        ["p1", "p2"], ["p2", "p3"], ["p3", "p4"],
    ]
    # joined token counts include the paragraph separator cost
    assert chunks[0].token_count == 12  # 5+5+2
    # page spans follow the grouped pages
    assert (chunks[1].page_start, chunks[1].page_end) == (1, 2)
    # determinism on re-run
    again = build_chunks(
        units, source_sha="sha", language=EN, config=ChunkConfig(max_tokens=16, overlap_tokens=6)
    )
    assert [c.chunk_id for c in again] == [c.chunk_id for c in chunks]


def test_different_budgets_change_grouping_not_text() -> None:
    units = [_u(f"p{i}", 1, 1, 1, "X", 4) for i in range(6)]
    small = build_chunks(
        units, source_sha="sha", language=EN, config=ChunkConfig(max_tokens=16, overlap_tokens=0)
    )
    large = build_chunks(
        units, source_sha="sha", language=EN, config=ChunkConfig(max_tokens=100, overlap_tokens=0)
    )
    assert len(small) > len(large) == 1
    # re-joining chunks with the standard paragraph separator restores the stream
    assert "\n\n".join(c.text for c in small) == "\n\n".join(c.text for c in large)


# ---------------------------------------------------------------- DB end to end


def _make_book(
    session: Session,
    sha256: str,
    language: str | None,
    texts: list[str],
    *,
    pages: list[int] | None = None,
) -> tuple[Book, SourceFile, Chapter, Section, list[ContentBlock]]:
    """One chapter / one section / one paragraph block per text."""
    source = SourceFile(
        sha256=sha256, file_path=f"books/{sha256}.pdf", format=SourceFormat.PDF
    )
    session.add(source)
    session.flush()
    book = Book(source_file_id=source.id, title="Chunk Fixture", language=language)
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, number=1, title="Chapter 1", source_file_id=source.id)
    session.add(chapter)
    session.flush()
    section = Section(
        book_id=book.id, chapter_id=chapter.id, number=1, title="Section 1",
        source_file_id=source.id,
    )
    session.add(section)
    session.flush()

    page_rows = {}
    blocks = []
    for idx, (text, page_no) in enumerate(
        zip(texts, pages or [1] * len(texts), strict=False), start=1
    ):
        if page_no not in page_rows:
            page = Page(
                book_id=book.id, source_file_id=source.id,
                page_number=page_no, has_text=True,
            )
            session.add(page)
            session.flush()
            page_rows[page_no] = page
        session.flush()
        block = ContentBlock(
            book_id=book.id,
            page_id=page_rows[page_no].id,
            chapter_id=chapter.id,
            section_id=section.id,
            source_file_id=source.id,
            block_type=BlockType.PARAGRAPH,
            sequence=idx,
            original_text=text,
        )
        session.add(block)
        blocks.append(block)
    session.flush()
    return book, source, chapter, section, blocks


TEXTS = ["First paragraph.", "Second paragraph.", "Third paragraph.",
         "Fourth paragraph.", "Fifth paragraph.", "Sixth paragraph."]


def _chunk_rows(session: Session, book_id: str) -> list[ContentChunk]:
    return session.scalars(
        select(ContentChunk)
        .where(ContentChunk.book_id == book_id)
        .order_by(ContentChunk.sequence)
    ).all()


def test_chunk_book_end_to_end_english(db: Session, tmp_path: Path) -> None:
    pages = [1, 1, 2, 2, 3, 3]
    book, source, chapter, section, blocks = _make_book(
        db, "11" * 32, "en", TEXTS, pages=pages
    )
    result = chunk_book(
        book, session=db, data_dir=tmp_path,
        config=ChunkConfig(max_tokens=16, overlap_tokens=0),
    )
    db.flush()

    assert result.error is None
    assert result.chunk_count >= 2
    assert result.paragraph_count == 6
    assert result.language == Language.ENGLISH

    rows = _chunk_rows(db, str(book.id))
    assert len(rows) == result.chunk_count
    assert rows[0].sequence == 0
    ids = {r.chunk_id for r in rows}
    assert len(ids) == len(rows)  # stable unique ids
    assert all(len(r.chunk_id) == 64 for r in rows)

    block_by_id = {str(blk.id): blk for blk in blocks}
    for row in rows:
        assert row.source_file_id == source.id
        assert row.chapter_id == chapter.id
        assert row.section_id == section.id
        assert row.language == Language.ENGLISH
        assert row.token_count == sum(
            estimate_tokens(block_by_id[bid].original_text, Language.ENGLISH)
            for bid in row.metadata_["block_ids"]
        ) + 2 * (len(row.metadata_["block_ids"]) - 1)  # \n\n separators
        assert row.content_block_id in {blk.id for blk in blocks}
        assert len(row.metadata_["block_ids"]) >= 1
        assert row.text == "\n\n".join(
            block_by_id[bid].original_text
            for bid in row.metadata_["block_ids"]
        )
        assert row.page_start and row.page_end
        assert row.is_normalized is False

    # every paragraph appears exactly once with no overlap configured
    seen = [bid for r in rows for bid in r.metadata_["block_ids"]]
    assert sorted(seen) == sorted(str(b.id) for b in blocks)

    report = tmp_path / "processed" / "chunk" / f"{'11' * 32}.txt"
    assert report.is_file()


def test_chunk_book_idempotent(db: Session, tmp_path: Path) -> None:
    book, _, _, _, _ = _make_book(db, "22" * 32, "en", TEXTS)
    config = ChunkConfig(max_tokens=60, overlap_tokens=0)
    first = chunk_book(book, session=db, data_dir=tmp_path, config=config)
    db.flush()
    db.expire_all()
    second = chunk_book(book, session=db, data_dir=tmp_path, config=config)
    db.flush()

    assert (first.chunk_count, first.token_total) == (second.chunk_count, second.token_total)
    first_ids = [r.chunk_id for r in _chunk_rows(db, str(book.id))]
    db.expire_all()
    second_ids = [r.chunk_id for r in _chunk_rows(db, str(book.id))]
    assert first_ids == second_ids  # stable, deterministic chunk ids
    count = db.scalar(
        select(func.count()).select_from(ContentChunk).where(
            ContentChunk.book_id == book.id
        )
    )
    assert count == first.chunk_count

    # originals untouched
    blocks = db.scalars(
        select(ContentBlock).where(ContentBlock.book_id == book.id).order_by(ContentBlock.sequence)
    ).all()
    assert [b.original_text for b in blocks] == TEXTS


def test_chunk_uses_normalized_variant_when_present(db: Session, tmp_path: Path) -> None:
    from knowledge_base.database.models.normalization import NormalizedText
    from knowledge_base.normalization.models import search_config
    from knowledge_base.normalization.normalize import normalize_text

    texts = ["لا إله إلا الله", "هذا نص عربي للاختبار"]
    book, _, _, _, blocks = _make_book(db, "33" * 32, "ar", texts)
    for block in blocks:
        res = normalize_text(block.original_text, search_config())
        db.add(
            NormalizedText(
                content_block_id=block.id,
                book_id=book.id,
                source_file_id=book.source_file_id,
                language=Language.ARABIC,
                config_name="search",
                normalized_text=res.normalized,
                original_sha256=_sha256(block.original_text),
                protected=res.stats.protected,
                stats=res.stats.model_dump(),
            )
        )
    db.flush()

    result = chunk_book(
        book, session=db, data_dir=tmp_path, config=ChunkConfig(max_tokens=200, overlap_tokens=0)
    )
    db.flush()
    assert result.error is None

    rows = _chunk_rows(db, str(book.id))
    assert rows[0].is_normalized is True
    norm_by_block = {
        str(b.id): b.original_text for b in blocks
    }
    # search variant folded and used as chunk text
    assert rows[0].text == "\n\n".join(
        normalize_text(norm_by_block[bid], search_config()).normalized
        for bid in rows[0].metadata_["block_ids"]
    )
    # original text on the blocks is untouched
    after = db.scalars(
        select(ContentBlock).where(ContentBlock.book_id == book.id).order_by(ContentBlock.sequence)
    ).all()
    assert [b.original_text for b in after] == texts


def test_chunk_urdu_uses_any_available_text(db: Session, tmp_path: Path) -> None:
    texts = ["یہ کتاب فقہ ہے۔", "دوسرا فقہی مضمون۔"]
    book, _, _, _, _ = _make_book(db, "44" * 32, "ur", texts)
    result = chunk_book(
        book, session=db, data_dir=tmp_path, config=ChunkConfig(max_tokens=200, overlap_tokens=0)
    )
    db.flush()
    assert result.error is None
    assert result.language == Language.URDU
    (row,) = _chunk_rows(db, str(book.id))
    assert row.is_normalized is False
    assert "فقہ" in row.text


def test_empty_book_error_and_failed_job(db: Session, tmp_path: Path) -> None:
    book, source, _, _, _ = _make_book(db, "55" * 32, "en", [])
    result = chunk_book(book, session=db, data_dir=tmp_path)
    db.flush()

    assert result.error is not None
    assert "no PARAGRAPH blocks" in result.error
    assert _chunk_rows(db, str(book.id)) == []
    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.CHUNK,
        )
    ).one()
    assert job.status == JobStatus.FAILED
    assert job.error == result.error
    assert job.manifest["chunk_count"] == 0


def test_job_manifest_succeeded(db: Session, tmp_path: Path) -> None:
    book, source, _, _, _ = _make_book(db, "66" * 32, "en", TEXTS)
    config = ChunkConfig(max_tokens=100, overlap_tokens=10)
    result = chunk_book(book, session=db, data_dir=tmp_path, config=config)
    db.flush()

    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.CHUNK,
        )
    ).one()
    assert job.status == JobStatus.SUCCEEDED
    assert job.error is None
    assert job.manifest["chunk_count"] == result.chunk_count
    assert job.manifest["max_tokens"] == 100
    assert job.manifest["overlap_tokens"] == 10
    assert job.manifest["paragraph_count"] == 6