"""Tests for the normalization pipeline stage.

Core invariant under test: normalization only ever *adds* a search-oriented
variant (``normalized_texts``) — it must never modify
``content_blocks.original_text``. We also verify that religious/protected and
non-paragraph content is never folded, per-language config selection, and that
re-running the stage is idempotent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import (
    BlockType,
    JobStatus,
    JobType,
    Language,
    SourceFormat,
)
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.normalization import NormalizedText
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.models.structure import ContentBlock, Page
from knowledge_base.normalization import conservative_config, search_config
from knowledge_base.pipeline.normalize.processor import (
    book_language,
    normalize_book,
    resolve_config,
)

BASMALA = "\uFDF2"
QURAN_OPEN = "\uFD3F"
QURAN_CLOSE = "\uFD3E"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_book(
    session: Session,
    sha256: str,
    language: str | None,
    paragraphs: list[str],
    *,
    extra_blocks: list[tuple[BlockType, str]] | None = None,
) -> tuple[Book, SourceFile]:
    """Create a book with one page of content blocks (paragraphs + extras)."""
    source = SourceFile(
        sha256=sha256, file_path=f"books/{sha256}.pdf", format=SourceFormat.PDF
    )
    session.add(source)
    session.flush()
    book = Book(
        source_file_id=source.id, title="Normalization Fixture", language=language
    )
    session.add(book)
    session.flush()
    page = Page(book_id=book.id, source_file_id=source.id, page_number=1, has_text=True)
    session.add(page)
    session.flush()

    seq = 0
    for text in paragraphs:
        seq += 1
        session.add(
            ContentBlock(
                book_id=book.id,
                page_id=page.id,
                source_file_id=source.id,
                block_type=BlockType.PARAGRAPH,
                sequence=seq,
                original_text=text,
            )
        )
    for block_type, text in extra_blocks or []:
        seq += 1
        session.add(
            ContentBlock(
                book_id=book.id,
                page_id=page.id,
                source_file_id=source.id,
                block_type=block_type,
                sequence=seq,
                original_text=text,
            )
        )
    session.flush()
    return book, source


def _originals(session: Session, book_id: str) -> dict[str, str]:
    blocks = session.scalars(
        select(ContentBlock).where(ContentBlock.book_id == book_id)
    ).all()
    return {str(b.id): b.original_text for b in blocks}


def _normalized_rows(session: Session, book_id: str) -> dict[str, NormalizedText]:
    rows = session.scalars(
        select(NormalizedText).where(NormalizedText.book_id == book_id)
    ).all()
    return {str(r.content_block_id): r for r in rows}


def _job(session: Session, source_file_id: str) -> ProcessingJob:
    return session.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source_file_id,
            ProcessingJob.job_type == JobType.NORMALIZE,
        )
    ).one()


# ----------------------------------------------------------- config resolution


def test_book_language_mapping() -> None:
    assert book_language(_book("ar")) == Language.ARABIC
    assert book_language(_book("ur")) == Language.URDU
    assert book_language(_book("en")) == Language.ENGLISH
    assert book_language(_book(None)) == Language.OTHER


def test_resolve_config_per_language() -> None:
    name, config = resolve_config("auto", Language.ARABIC)
    assert name == "search"
    assert config == search_config()

    name, config = resolve_config("auto", Language.URDU)
    assert name == "urdu"
    assert config.normalize_digits is True
    assert config.urdu_normalization is False  # Urdu letters stay distinct

    name, config = resolve_config("auto", Language.ENGLISH)
    assert name == "conservative"
    assert config == conservative_config()

    name, _ = resolve_config("auto", Language.OTHER)
    assert name == "conservative"

    name, _ = resolve_config("conservative", Language.ARABIC)
    assert name == "conservative"
    name, _ = resolve_config("search", Language.ENGLISH)
    assert name == "search"


# --------------------------------------------------------------- end to end


AR_PAGES = [
    f"{BASMALA} الرحمن الرحيم",
    f"{QURAN_OPEN}قُلْ هُوَ اللَّهُ أَحَدٌ{QURAN_CLOSE}",
    "لا إله إلا اللهُ أبدًا",
]


def test_original_text_byte_identical_after_normalize(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "aa" * 32, "ar", AR_PAGES)
    before = _originals(db, str(book.id))

    result = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    assert result.error is None
    assert result.language == Language.ARABIC
    assert result.config_name == "search"
    assert result.blocks_total == 3
    assert result.blocks_normalized == 3
    assert result.blocks_protected == 2
    assert result.blocks_skipped == 0

    # originals untouched
    after = _originals(db, str(book.id))
    assert after == before

    rows = _normalized_rows(db, str(book.id))
    assert len(rows) == 3

    for block_id, original in before.items():
        row = rows[block_id]
        assert row.original_sha256 == _sha256(original)
        assert row.language == Language.ARABIC

        orb = next(
            b for b in db.scalars(select(ContentBlock)).all()
            if str(b.id) == block_id
        )
        assert orb.original_text == original

    by_text = {r.normalized_text: r for r in rows.values()}
    protected_text = next(
        t for t in by_text if QURAN_OPEN in t
    )
    assert by_text[protected_text].protected is True
    # protected religious text: never folded, variant equals original
    assert by_text[protected_text].normalized_text == next(
        b.original_text for b in db.scalars(select(ContentBlock)).all()
        if b.block_type == BlockType.PARAGRAPH and QURAN_OPEN in b.original_text
    )
    # plain prose got a hamza/alef fold: original ${'إله'} preserved, variant folded
    folded = next(r for r in rows.values() if "إله" in next(
        b.original_text for b in db.scalars(select(ContentBlock)).all()
        if str(b.id) == str(r.content_block_id)
    ))
    assert "لا اله" in folded.normalized_text
    # the original itself is untouched
    assert any("إله" in b.original_text for b in db.scalars(select(ContentBlock)).all())

    report = tmp_path / "processed" / "normalized" / f"{'aa' * 32}.txt"
    assert report.is_file()


def test_protected_and_non_paragraph_blocks_never_folded(
    db: Session, tmp_path: Path
) -> None:
    extras = [
        (BlockType.VERSE, f"{QURAN_OPEN}يَاأَيُّهَا الَّذِينَ آمَنُوا{QURAN_CLOSE}"),
        (BlockType.HADITH, "قَالَ رَسُولُ اللَّهِ ﷺ: لَا يُؤْمِنُ أَحَدُكُمْ"),
        (BlockType.REFERENCE, "البخاري، صحيح البخاري، كتاب الإيمان"),
        (BlockType.FOOTNOTE, "(١) انظر المصدر السابق."),
        (BlockType.HEADING, "الباب الأول في الطهارة"),
    ]
    book, _ = _make_book(db, "bb" * 32, "ar", ["إحداث فرق نصي هنا"], extra_blocks=extras)
    result = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    assert result.blocks_total == 6
    assert result.blocks_normalized == 1  # only the paragraph
    assert result.blocks_skipped == 5

    rows = _normalized_rows(db, str(book.id))
    assert len(rows) == 1
    (row,) = rows.values()
    assert row.protected is False
    assert row.original_sha256 == _sha256("إحداث فرق نصي هنا")

    # every non-paragraph block still matches its untouched original
    blocks = db.scalars(
        select(ContentBlock).where(
            ContentBlock.book_id == book.id,
            ContentBlock.block_type != BlockType.PARAGRAPH,
        )
    ).all()
    assert len(blocks) == 5
    for block in blocks:
        assert block.original_text
        verse = next(
            (b for b in blocks if b.block_type == BlockType.VERSE), None
        )
        assert verse is not None
        assert verse.original_text == f"{QURAN_OPEN}يَاأَيُّهَا الَّذِينَ آمَنُوا{QURAN_CLOSE}"


def test_urdu_digits_normalized_letters_preserved(db: Session, tmp_path: Path) -> None:
    text = "یہ کتاب فقہ ۱۲۳۴ ہے۔"
    book, _ = _make_book(db, "cc" * 32, "ur", [text])
    result = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    assert result.config_name == "urdu"
    (row,) = _normalized_rows(db, str(book.id)).values()
    # Urdu-Indic numerals normalized for search parity
    assert "1234" in row.normalized_text
    assert "۱۲۳۴" not in row.normalized_text
    # Urdu letters keep their distinct identity (no folding)
    assert "یہ" in row.normalized_text
    assert "کتاب" in row.normalized_text
    # original verbatim on the block
    block = db.scalars(select(ContentBlock).where(ContentBlock.book_id == book.id)).one()
    assert block.original_text == text


def test_english_conservative_no_folds(db: Session, tmp_path: Path) -> None:
    text = "Peace and blessings be upon the Messenger."
    book, _ = _make_book(db, "dd" * 32, "en", [text])
    result = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    assert result.config_name == "conservative"
    assert result.unchanged == 1
    (row,) = _normalized_rows(db, str(book.id)).values()
    assert row.normalized_text == text
    assert row.protected is False


def test_rerun_is_idempotent(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "ee" * 32, "ar", AR_PAGES)
    before = _originals(db, str(book.id))
    first = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()
    db.expire_all()

    second = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    assert (first.blocks_total, first.blocks_normalized) == (
        second.blocks_total, second.blocks_normalized,
    )
    assert _originals(db, str(book.id)) == before
    rows = _normalized_rows(db, str(book.id))
    assert len(rows) == 3
    count = db.scalar(
        select(func.count()).select_from(NormalizedText).where(
            NormalizedText.book_id == book.id
        )
    )
    assert count == 3
    assert all(
        row.original_sha256 == _sha256(before[str(row.content_block_id)])
        for row in rows.values()
    )


def test_job_manifest_and_status(db: Session, tmp_path: Path) -> None:
    book, source = _make_book(db, "ff" * 32, "ar", AR_PAGES)
    normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    job = _job(db, str(source.id))
    assert job.status == JobStatus.SUCCEEDED
    assert job.error is None
    assert job.manifest["language"] == "ar"
    assert job.manifest["config"] == "search"
    assert job.manifest["blocks_normalized"] == 3


def test_empty_book_returns_error_and_failed_job(db: Session, tmp_path: Path) -> None:
    book, source = _make_book(db, "11" * 32, "en", [])
    result = normalize_book(book, session=db, data_dir=tmp_path, config_name="auto")
    db.flush()

    assert result.error is not None
    assert "no content blocks" in result.error
    assert _normalized_rows(db, str(book.id)) == {}
    job = _job(db, str(source.id))
    assert job.status == JobStatus.FAILED
    assert job.error == result.error


def _book(language: str | None) -> Book:
    book = Book(title="_probe")
    book.language = language
    return book