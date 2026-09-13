"""Database schema tests: relationships, constraints, cascades, provenance.

These tests run against a PostgreSQL test database (the docker pgvector
container, port 5434). They are skipped when the test database is not
reachable so the suite stays runnable without infra.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowledge_base.database.base import Base

_TEST_URL = os.environ.get(
    "KB_TEST_DATABASE_URL",
    "postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test",
)


def _module_tables() -> set[str]:
    return set(Base.metadata.tables.keys())


def _commit(session: Session) -> None:
    session.commit()
    session.begin()


# ---------------------------------------------------------------- sources


def test_source_file_unique_sha256(db: Session) -> None:
    from knowledge_base.database.models.sources import SourceFile, SourceFormat

    db.add(
        SourceFile(
            sha256="a" * 64,
            file_path="/raw/quran/x.txt",
            format=SourceFormat.TXT,
            status="registered",
        )
    )
    _commit(db)
    db.add(
        SourceFile(
            sha256="a" * 64,
            file_path="/raw/quran/y.txt",
            format=SourceFormat.TXT,
            status="registered",
        )
    )
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


def test_source_file_stable_uuid(db: Session) -> None:
    from knowledge_base.database.models.sources import SourceFile, SourceFormat

    sf = SourceFile(sha256="b" * 64, file_path="/x.pdf", format=SourceFormat.PDF)
    sf2 = SourceFile(sha256="c" * 64, file_path="/y.pdf", format=SourceFormat.PDF)
    db.add_all([sf, sf2])
    _commit(db)
    assert isinstance(sf.id, uuid.UUID)
    assert sf.id != sf2.id


def test_source_editions_cascade(db: Session) -> None:
    from knowledge_base.database.models.sources import (
        SourceEdition,
        SourceFile,
        SourceFormat,
    )

    sf = SourceFile(sha256="d" * 64, file_path="/raw/book.pdf", format=SourceFormat.PDF)
    sf.editions.append(SourceEdition(title="Hidayah", language="ar"))
    db.add(sf)
    _commit(db)
    assert len(sf.editions) == 1

    db.delete(sf)
    _commit(db)
    count = db.execute(
        select(text("count(1)")).select_from(text("source_editions"))
    ).scalar_one()
    assert count == 0


def test_processing_job_unique_file_type(db: Session) -> None:
    from knowledge_base.database.models.sources import (
        JobStatus,
        JobType,
        ProcessingJob,
        SourceFile,
        SourceFormat,
    )

    sf = SourceFile(sha256="e" * 64, file_path="/raw/book.pdf", format=SourceFormat.PDF)
    db.add(sf)
    _commit(db)
    db.add(
        ProcessingJob(
            source_file_id=sf.id,
            job_type=JobType.INSPECT,
            status=JobStatus.RUNNING,
        )
    )
    _commit(db)
    db.add(
        ProcessingJob(
            source_file_id=sf.id,
            job_type=JobType.INSPECT,
            status=JobStatus.SUCCEEDED,
        )
    )
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


# ---------------------------------------------------------------- books


def _make_book_chain(db: Session) -> dict[str, Any]:
    from knowledge_base.database.models.books import (
        Author,
        Book,
        Category,
        Publisher,
        Topic,
    )
    from knowledge_base.database.models.sources import (
        SourceEdition,
        SourceFile,
        SourceFormat,
    )

    sf = SourceFile(
        sha256="f" * 64,
        file_path="/raw/books/fiqh/hidayah.pdf",
        format=SourceFormat.PDF,
    )
    edition = SourceEdition(title="Al-Hidayah", language="ar")
    sf.editions.append(edition)
    db.add(sf)
    db.flush()

    author = Author(name="Burhan al-Din al-Marghinani", name_arabic="برهان الدين المرغيناني")
    publisher = Publisher(name="Dar Kutub", city="Beirut")
    category = Category(code="fiqh", name="Islamic Jurisprudence")
    topic = Topic(name="Hanafi fiqh", category=category)

    book = Book(
        title="Al-Hidayah",
        source_file_id=sf.id,
        edition=edition,
        author=author,
        publisher=publisher,
        category=category,
    )
    book.topics.append(topic)
    db.add(book)
    _commit(db)
    return {"sf": sf, "edition": edition, "book": book, "author": author}


def test_book_provenance_chain(db: Session) -> None:
    from knowledge_base.database.models.books import Book

    data = _make_book_chain(db)
    book = db.scalar(select(Book).where(Book.id == data["book"].id))
    assert book is not None
    assert book.source_file_id == data["sf"].id
    assert book.edition is not None
    assert book.edition.source_file is data["sf"]
    assert book.author.name == "Burhan al-Din al-Marghinani"
    assert book.category.code == "fiqh"
    assert len(book.topics) == 1


def test_book_rejects_unknown_source(db: Session) -> None:
    from knowledge_base.database.models.books import Book

    db.add(Book(title="Bogus", source_file_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


def test_author_unique_name(db: Session) -> None:
    from knowledge_base.database.models.books import Author

    db.add(Author(name="Ibn Kathir"))
    _commit(db)
    db.add(Author(name="Ibn Kathir"))
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


def test_book_topics_many_to_many(db: Session) -> None:
    from knowledge_base.database.models.books import Topic

    data = _make_book_chain(db)
    other_topic = Topic(name="Usul al-fiqh", category_id=data["book"].category_id)
    data["book"].topics.append(other_topic)
    db.add(other_topic)
    _commit(db)
    assert len(data["book"].topics) == 2


# ---------------------------------------------------------------- structure


def test_book_structure_provenance(db: Session) -> None:
    from knowledge_base.database.models.structure import (
        Chapter,
        ContentBlock,
        ContentChunk,
        Page,
        Paragraph,
        Section,
    )

    data = _make_book_chain(db)
    book, sf = data["book"], data["sf"]

    chapter = Chapter(book=book, source_file=sf, number=1, title="Kitab al-Tahara")
    section = Section(
        book=book, chapter=chapter, source_file=sf, number=1, title="Water types"
    )
    page = Page(book=book, source_file=sf, page_number=7, has_text=True)
    para = Paragraph(
        book=book,
        page=page,
        source_file=sf,
        sequence=1,
        text="Original paragraph text.",
    )
    block = ContentBlock(
        book=book,
        page=page,
        chapter=chapter,
        section=section,
        source_file=sf,
        block_type="paragraph",
        sequence=1,
        original_text="Original paragraph text.",
        status="pending",
    )
    chunk = ContentChunk(
        chunk_id=f"{sf.sha256}:007:001",
        book=book,
        content_block=block,
        source_file=sf,
        page_start=7,
        page_end=7,
        sequence=1,
        text="Original paragraph text.",
        language="en",
        token_count=3,
        status="pending",
    )
    db.add_all([chapter, section, page, para, block, chunk])
    _commit(db)

    # Every hop resolves back to the source file.
    assert chunk.source_file_id == sf.id
    assert chunk.content_block.source_file_id == sf.id
    assert chunk.content_block.page.page_number == 7
    assert chunk.content_block.chapter.number == 1
    assert chunk.book.title == "Al-Hidayah"


def test_structure_cascade_delete(db: Session) -> None:
    from knowledge_base.database.models.structure import Chapter

    data = _make_book_chain(db)
    book, sf = data["book"], data["sf"]
    chapter = Chapter(book=book, source_file=sf, number=2, title="Kitab al-Salah")
    db.add(chapter)
    _commit(db)
    assert db.scalar(select(text("count(1)")).select_from(text("chapters"))) == 1

    db.delete(book)
    _commit(db)
    assert db.scalar(select(text("count(1)")).select_from(text("chapters"))) == 0


def test_chunk_duplicate_id_rejected(db: Session) -> None:
    from knowledge_base.database.models.structure import (
        ContentBlock,
        ContentChunk,
        Page,
    )

    data = _make_book_chain(db)
    book, sf = data["book"], data["sf"]
    page = Page(book=book, source_file=sf, page_number=1, has_text=False)
    block = ContentBlock(
        book=book,
        page=page,
        source_file=sf,
        block_type="heading",
        sequence=1,
        original_text="Title",
        status="pending",
    )
    db.add_all([page, block])
    _commit(db)

    db.add(
        ContentChunk(
            chunk_id="dup-1",
            book=book,
            content_block=block,
            source_file=sf,
            page_start=1,
            page_end=1,
            sequence=1,
            text="a",
            language="en",
            token_count=1,
            status="pending",
        )
    )
    _commit(db)
    db.add(
        ContentChunk(
            chunk_id="dup-1",
            book=book,
            content_block=block,
            source_file=sf,
            page_start=1,
            page_end=1,
            sequence=2,
            text="b",
            language="en",
            token_count=1,
            status="pending",
        )
    )
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


# ---------------------------------------------------------------- quran


def test_quran_natural_keys(db: Session) -> None:
    from knowledge_base.database.models.quran import Ayah, Surah, Translation

    sf = _make_book_chain(db)["sf"]
    al_fatiha = Surah(number=1, name_arabic="الفاتحة", name_en="The Opening", ayah_count=7)
    db.add(al_fatiha)
    _commit(db)

    ayah = Ayah(
        surah=al_fatiha,
        source_file=sf,
        number=1,
        text="بِسْمِ اللهِ الرَّحْمَنِ الرَّحِيمِ",
        page_number=1,
        juz=1,
    )
    db.add(ayah)
    _commit(db)

    db.add(
        Translation(
            ayah=ayah,
            source_file=sf,
            language="en",
            translator="Yusuf Ali",
            text="In the name of Allah, Most Gracious, Most Merciful.",
        )
    )
    _commit(db)

    assert ayah.surah.number == 1
    assert ayah.translations[0].language == "en"
    assert ayah.number == 1


def test_ayah_same_number_in_surah_surah_rejected(db: Session) -> None:
    from knowledge_base.database.models.quran import Ayah, Surah

    sf = _make_book_chain(db)["sf"]
    surah = Surah(number=2, name_arabic="البقرة")
    db.add(surah)
    _commit(db)
    db.add(Ayah(surah=surah, source_file=sf, number=1, text="a"))
    _commit(db)
    db.add(Ayah(surah=surah, source_file=sf, number=1, text="b"))
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


# ---------------------------------------------------------------- hadith


def test_hadith_provenance(db: Session) -> None:
    from knowledge_base.database.models.hadith import (
        Collection,
        Hadith,
        HadithBook,
        HadithChapter,
    )

    sf = _make_book_chain(db)["sf"]
    bukhari = Collection(
        name="sahih-bukhari", title="Sahih al-Bukhari", author="Muhammad al-Bukhari"
    )
    book = HadithBook(collection=bukhari, name="Kitab al-Iman")
    chapter = HadithChapter(collection=bukhari, hadith_book=book, name="Bab al-Iman")
    hadith = Hadith(
        collection=bukhari,
        hadith_book=book,
        hadith_chapter=chapter,
        source_file=sf,
        number=1,
        text="Imam al-Bukhari begins...",
        grade="sahih",
    )
    db.add_all([bukhari, book, chapter, hadith])
    _commit(db)

    assert hadith.collection.name == "sahih-bukhari"
    assert hadith.source_file_id == sf.id
    assert hadith.hadith_chapter.hadith_book.name == "Kitab al-Iman"


def test_hadith_unique_number_in_collection(db: Session) -> None:
    from knowledge_base.database.models.hadith import Collection, Hadith

    sf = _make_book_chain(db)["sf"]
    coll = Collection(name="sahih-muslim")
    db.add(coll)
    _commit(db)
    db.add(Hadith(collection=coll, source_file=sf, number=1, text="first"))
    _commit(db)
    db.add(Hadith(collection=coll, source_file=sf, number=1, text="second"))
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


# ---------------------------------------------------------------- search + embeddings


def test_search_document_links_chunk(db: Session) -> None:
    from knowledge_base.database.models.search import SearchDocument
    from knowledge_base.database.models.structure import ContentBlock, ContentChunk, Page

    data = _make_book_chain(db)
    book, sf = data["book"], data["sf"]
    page = Page(book=book, source_file=sf, page_number=3, has_text=True)
    block = ContentBlock(
        book=book,
        page=page,
        source_file=sf,
        block_type="paragraph",
        sequence=1,
        original_text="جملة للبحث",
        status="validated",
    )
    chunk = ContentChunk(
        chunk_id=f"{sf.sha256}:003:001",
        book=book,
        content_block=block,
        source_file=sf,
        page_start=3,
        page_end=3,
        sequence=1,
        text="جملة للبحث",
        language="ar",
        token_count=4,
        status="validated",
    )
    doc = SearchDocument(
        chunk=chunk,
        document_type="chunk",
        language="ar",
        title=None,
        body_text="جملة للبحث",
    )
    db.add_all([page, block, chunk, doc])
    _commit(db)
    assert doc.chunk == chunk
    assert doc.chunk.book.title == "Al-Hidayah"


def test_embedding_model_and_vector(db: Session) -> None:
    from knowledge_base.database.models.embeddings import Embedding, EmbeddingModel
    from knowledge_base.database.models.structure import ContentBlock, ContentChunk, Page

    data = _make_book_chain(db)
    book, sf = data["book"], data["sf"]
    model = EmbeddingModel(name="test-mini", provider="local", dimensions=768, version="1.0")
    db.add(model)
    _commit(db)

    page = Page(book=book, source_file=sf, page_number=4, has_text=True)
    block = ContentBlock(
        book=book,
        page=page,
        source_file=sf,
        block_type="paragraph",
        sequence=1,
        original_text="vector probe",
        status="published",
    )
    chunk = ContentChunk(
        chunk_id=f"{sf.sha256}:004:001",
        book=book,
        content_block=block,
        source_file=sf,
        page_start=4,
        page_end=4,
        sequence=1,
        text="vector probe",
        language="en",
        token_count=2,
        status="published",
    )
    db.add_all([page, block, chunk])
    _commit(db)

    vector = [0.01] * 768
    db.add(Embedding(model=model, chunk=chunk, vector=vector))
    _commit(db)

    emb = db.scalar(select(Embedding).where(Embedding.content_chunk_id == chunk.id))
    assert emb is not None
    assert abs(sum(emb.vector) - 768 * 0.01) < 1e-6


def test_embedding_model_version_unique(db: Session) -> None:
    from knowledge_base.database.models.embeddings import EmbeddingModel

    db.add(EmbeddingModel(name="m1", provider="p", dimensions=768, version="1"))
    _commit(db)
    db.add(EmbeddingModel(name="m1", provider="p", dimensions=768, version="1"))
    with pytest.raises(IntegrityError):
        _commit(db)
        db.rollback()


def test_timestamps_are_server_default(db: Session) -> None:
    from knowledge_base.database.models.books import Category

    category = Category(code="tafsir", name="Tafsir")
    db.add(category)
    _commit(db)
    assert category.created_at is not None
    assert category.updated_at is not None


def test_schema_tables_present(db_engine: Engine) -> None:
    tables = set(_module_tables())
    created = {
        row[0]
        for row in db_engine.connect().execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        )
    }
    assert tables <= created
    assert "vector" in {
        row[0]
        for row in db_engine.connect().execute(text("SELECT extname FROM pg_extension"))
    }