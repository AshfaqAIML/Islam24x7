"""Seed the hadith domain from a validated dataset."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.models.hadith import Collection, Hadith, HadithBook, HadithChapter
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.pipeline.seed.datasets import HadithDataset, HadithPayload
from knowledge_base.pipeline.seed.report import SeedConflictError, SeedReport


def seed_hadith(session: Session, source_file: SourceFile, dataset: HadithDataset) -> SeedReport:
    """Load one hadith collection and its hadiths, ignoring already-seeded rows.

    Idempotency: the natural key is (collection, number). Books and chapters are
    keyed within the collection by name. Existing hadiths are skipped when their
    text matches; a mismatch raises ``SeedConflictError``.
    """
    report = SeedReport(kind="hadith")
    source_file_id = source_file.id

    collection = session.scalar(select(Collection).where(Collection.name == dataset.collection))
    if collection is None:
        collection = Collection(
            name=dataset.collection,
            title=dataset.title,
            author=dataset.author,
            description=dataset.description,
        )
        session.add(collection)
        session.flush()
        report.created += 1
    else:
        report.skipped += 1

    for payload in dataset.hadiths:
        _upsert_hadith(session, collection, source_file_id, payload, report)

    return report


def _upsert_hadith(
    session: Session,
    collection: Collection,
    source_file_id: UUID,
    payload: HadithPayload,
    report: SeedReport,
) -> None:
    hadith_book = None
    if payload.book:
        hadith_book = _get_or_create_book(session, collection, payload.book, report)
    hadith_chapter = None
    if payload.chapter:
        hadith_chapter = _get_or_create_chapter(
            session, collection, hadith_book, payload.chapter, report
        )

    hadith = session.scalar(
        select(Hadith).where(Hadith.collection_id == collection.id, Hadith.number == payload.number)
    )
    if hadith is None:
        session.add(
            Hadith(
                collection_id=collection.id,
                hadith_book_id=hadith_book.id if hadith_book else None,
                hadith_chapter_id=hadith_chapter.id if hadith_chapter else None,
                source_file_id=source_file_id,
                number=payload.number,
                text=payload.text,
                text_arabic=payload.text_arabic,
                grade=payload.grade,
                narrator=payload.narrator,
            )
        )
        report.created += 1
    elif hadith.text != payload.text:
        raise SeedConflictError(
            f"{collection.name} {payload.number} already exists with "
            "different text; refusing to overwrite"
        )
    else:
        report.skipped += 1


def _get_or_create_book(
    session: Session, collection: Collection, name: str, report: SeedReport
) -> HadithBook:
    book = session.scalar(
        select(HadithBook).where(HadithBook.collection_id == collection.id, HadithBook.name == name)
    )
    if book is None:
        book = HadithBook(collection_id=collection.id, name=name)
        session.add(book)
        session.flush()
        report.created += 1
    return book


def _get_or_create_chapter(
    session: Session,
    collection: Collection,
    hadith_book: HadithBook | None,
    name: str,
    report: SeedReport,
) -> HadithChapter:
    stmt = select(HadithChapter).where(
        HadithChapter.collection_id == collection.id, HadithChapter.name == name
    )
    if hadith_book is not None:
        stmt = stmt.where(HadithChapter.hadith_book_id == hadith_book.id)
    chapter = session.scalar(stmt)
    if chapter is None:
        chapter = HadithChapter(
            collection_id=collection.id,
            hadith_book_id=hadith_book.id if hadith_book else None,
            name=name,
        )
        session.add(chapter)
        session.flush()
        report.created += 1
    return chapter
