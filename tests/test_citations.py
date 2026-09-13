"""Tests for the universal source-provenance citation system.

Citations must originate from actual database records: the builders read every
field off loaded ORM rows and their relationships, reject non-matching record
types, and never fabricate values. We verify the full lineage for each domain
(book/chunk, quran/ayah/translation, hadith) and the stable JSON contract.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from knowledge_base.citations import (
    citation_from_ayah,
    citation_from_chunk,
    citation_from_db,
    citation_from_hadith,
    citation_from_translation,
)
from knowledge_base.database.enums import BlockType, Language, SourceFormat
from knowledge_base.database.models.books import Author, Book, Category
from knowledge_base.database.models.hadith import (
    Collection,
    Hadith,
    HadithBook,
    HadithChapter,
)
from knowledge_base.database.models.quran import Ayah, Surah, Translation
from knowledge_base.database.models.sources import SourceEdition, SourceFile
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Page,
    Section,
)


def _source(
    session: Session, sha256: str, fmt: SourceFormat = SourceFormat.PDF
) -> SourceFile:
    source = SourceFile(sha256=sha256, file_path=f"books/{sha256}.pdf", format=fmt)
    session.add(source)
    session.flush()
    return source


def _book_to_chunk(session: Session, sha256: str) -> tuple[Book, ContentChunk]:
    sf = _source(session, sha256)
    author = Author(name="Imam Anon")
    session.add(author)
    session.flush()
    edition = SourceEdition(source_file_id=sf.id, title="First Edition", language="en")
    session.add(edition)
    session.flush()
    book = Book(
        source_file_id=sf.id, edition_id=edition.id, title="Tadhkirah",
        author_id=author.id, language="en",
    )
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, number=1, title="Chapter One", source_file_id=sf.id)
    session.add(chapter)
    session.flush()
    section = Section(
        book_id=book.id, chapter_id=chapter.id, number=1, title="Section Alpha",
        source_file_id=sf.id,
    )
    session.add(section)
    session.flush()
    page = Page(book_id=book.id, source_file_id=sf.id, page_number=12, has_text=True)
    session.add(page)
    session.flush()
    block = ContentBlock(
        book_id=book.id, page_id=page.id, chapter_id=chapter.id, section_id=section.id,
        source_file_id=sf.id, block_type=BlockType.PARAGRAPH, sequence=1,
        original_text="patience in hardship", status="published",
    )
    session.add(block)
    session.flush()
    chunk = ContentChunk(
        chunk_id=f"{sf.sha256}:012:001",
        book_id=book.id, content_block_id=block.id, source_file_id=sf.id,
        chapter_id=chapter.id, section_id=section.id, language=Language.ENGLISH,
        token_count=4, page_start=12, page_end=13, sequence=1,
        text="patience in hardship", status="published",
    )
    session.add(chunk)
    session.flush()
    return book, chunk


# ----------------------------------------------------------------- book

def test_chunk_citation_has_full_book_lineage(db: Session) -> None:
    book, chunk = _book_to_chunk(db, "aa" * 32)
    citation = citation_from_chunk(chunk)

    assert citation.source_type == "book"
    assert citation.book_id == str(book.id)
    assert citation.book_title == "Tadhkirah"
    assert citation.edition_id == str(book.edition.id)
    assert citation.edition_title == "First Edition"
    assert citation.chapter_id == str(chunk.chapter_id)
    assert citation.chapter_title == "Chapter One"
    assert citation.section_id == str(chunk.section_id)
    assert citation.section_title == "Section Alpha"
    assert citation.page_start == 12
    assert citation.page_end == 13
    assert citation.page == 12
    assert citation.content_id == str(chunk.id)
    assert citation.chunk_id == chunk.chunk_id
    assert citation.source_file_id == str(chunk.source_file_id)
    assert citation.source_sha256 == "aa" * 32
    assert "Tadhkirah" in citation.reference()
    assert chunk.chunk_id in citation.reference()


def test_chunk_citation_dict_contract_matches_example(db: Session) -> None:
    book, chunk = _book_to_chunk(db, "ab" * 32)
    data = citation_from_db(chunk).to_dict()

    assert data["source_type"] == "book"
    assert data["book_id"] == str(book.id)
    assert data["chapter_id"] == str(chunk.chapter_id)
    assert data["page_start"] == 12
    assert data["page_end"] == 13
    assert data["content_id"] == str(chunk.id)
    assert data["chunk_id"] == chunk.chunk_id

    json.loads(citation_from_db(chunk).to_json())  # serializable


def test_chunk_citation_is_database_origin_truthful(db: Session) -> None:
    """Every reported value matches the actual rows — nothing invented."""
    _, chunk = _book_to_chunk(db, "ac" * 32)
    data = citation_from_db(chunk).to_dict()
    book = chunk.book
    assert data["book_id"] == str(book.id)
    assert data["edition_id"] == str(book.edition.id)
    assert data["source_sha256"] == chunk.source_file.sha256


def test_chunk_citation_rejects_foreign_types(db: Session) -> None:
    category = Category(code="fiqh", name="Fiqh")
    db.add(category)
    db.flush()
    with pytest.raises(TypeError, match="ContentChunk"):
        citation_from_chunk(category)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="no citation"):
        citation_from_db(category)


# ---------------------------------------------------------------- quran

def test_ayah_citation_lineage(db: Session) -> None:
    sf = _source(db, "ad" * 32)
    surah = Surah(number=2, name_arabic="البقرة", name_en="Al-Baqarah", ayah_count=286)
    db.add(surah)
    db.flush()
    ayah = Ayah(
        surah_id=surah.id, source_file_id=sf.id, number=255, text="...",
        page_number=42, juz=3,
    )
    db.add(ayah)
    db.flush()

    citation = citation_from_ayah(ayah)
    assert citation.source_type == "quran"
    assert citation.surah_id == str(surah.id)
    assert citation.surah_number == 2
    assert citation.surah_name == "البقرة"
    assert citation.ayah_id == str(ayah.id)
    assert citation.ayah_number == 255
    assert citation.page == 42
    assert citation.source_sha256 == "ad" * 32
    assert citation.reference() == "البقرة:255"


def test_translation_citation_preserves_ayah_lineage(db: Session) -> None:
    sf = _source(db, "ae" * 32)
    surah = Surah(number=2, name_arabic="البقرة", name_en="Al-Baqarah", ayah_count=286)
    db.add(surah)
    db.flush()
    ayah = Ayah(surah_id=surah.id, source_file_id=sf.id, number=255, text="...")
    db.add(ayah)
    db.flush()
    trans = Translation(
        ayah_id=ayah.id, source_file_id=sf.id, language="en",
        translator="Pickthall", text="Allah, there is no god but he",
    )
    db.add(trans)
    db.flush()

    citation = citation_from_translation(trans)
    assert citation.source_type == "quran"
    assert citation.ayah_id == str(ayah.id)
    assert citation.ayah_number == 255
    assert citation.surah_number == 2
    assert citation.translation_language == "en"
    assert citation.translator == "Pickthall"
    assert citation.source_sha256 == "ae" * 32
    assert "en by Pickthall" in citation.reference()


def test_quran_builders_reject_wrong_types(db: Session) -> None:
    sf = _source(db, "af" * 32)
    surah = Surah(number=1, name_arabic="الفاتحة", ayah_count=7)
    db.add(surah)
    db.flush()
    ayah = Ayah(surah_id=surah.id, source_file_id=sf.id, number=1, text="...")
    db.add(ayah)
    db.flush()
    with pytest.raises(TypeError, match="Ayah"):
        citation_from_ayah(surah)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Translation"):
        citation_from_translation(ayah)  # type: ignore[arg-type]
    assert citation_from_db(ayah).reference() == "الفاتحة:1"


# ---------------------------------------------------------------- hadith

def test_hadith_citation_lineage(db: Session) -> None:
    sf = _source(db, "b0" * 32)
    collection = Collection(name="bukhari", title="Sahih al-Bukhari", author="Al-Bukhari")
    db.add(collection)
    db.flush()
    hbook = HadithBook(collection_id=collection.id, name="Kitab al-Iman")
    db.add(hbook)
    db.flush()
    hchapter = HadithChapter(collection_id=collection.id, hadith_book_id=hbook.id, name="Baab 1")
    db.add(hchapter)
    db.flush()
    hadith = Hadith(
        collection_id=collection.id, hadith_book_id=hbook.id,
        hadith_chapter_id=hchapter.id, source_file_id=sf.id, number=7,
        text="Actions are but by intentions",
    )
    db.add(hadith)
    db.flush()

    citation = citation_from_db(hadith)
    assert citation.source_type == "hadith"
    assert citation.collection_id == str(collection.id)
    assert citation.collection_name == "Sahih al-Bukhari"
    assert citation.hadith_book_id == str(hbook.id)
    assert citation.hadith_book_name == "Kitab al-Iman"
    assert citation.hadith_chapter_id == str(hchapter.id)
    assert citation.hadith_chapter_name == "Baab 1"
    assert citation.hadith_id == str(hadith.id)
    assert citation.hadith_number == 7
    assert citation.source_sha256 == "b0" * 32
    assert "#7" in citation.reference()
    assert "Kitab al-Iman" in citation.reference()


def test_hadith_citation_rejects_wrong_type(db: Session) -> None:
    sf = _source(db, "b1" * 32)
    collection = Collection(name="muslim", title="Sahih Muslim")
    db.add(collection)
    db.flush()
    hadith = Hadith(collection_id=collection.id, source_file_id=sf.id, number=1, text="...")
    db.add(hadith)
    db.flush()
    with pytest.raises(TypeError, match="Hadith"):
        citation_from_hadith(collection)  # type: ignore[arg-type]
    assert citation_from_db(hadith).source_type == "hadith"