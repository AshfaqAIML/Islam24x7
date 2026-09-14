"""Tests for the full-text search milestone.

Covers the ``INDEX`` pipeline stage (search_documents materialization, job
records, idempotency) and the search engine end to end: keyword matching,
exact phrases, multi-term any/all, catalog domains (book/chapter/section),
content provenance, quran (Arabic + translations), hadith, and every filter.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from knowledge_base.database.enums import (
    BlockType,
    JobStatus,
    JobType,
    Language,
    SourceFormat,
)
from knowledge_base.database.models.books import Author, Book, Category
from knowledge_base.database.models.hadith import Collection, Hadith
from knowledge_base.database.models.quran import Ayah, Surah, Translation
from knowledge_base.database.models.search import SearchDocument
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Page,
    Section,
)
from knowledge_base.pipeline.chunk.config import ChunkConfig
from knowledge_base.pipeline.chunk.processor import chunk_book
from knowledge_base.pipeline.index.index import index_book
from knowledge_base.search import SearchParams, search
from knowledge_base.search.arabic import normalize_arabic_search


def _make_book(
    session: Session,
    sha256: str,
    language: str | None,
    texts: list[str],
    *,
    title: str = "Search Fixture",
    pages: list[int] | None = None,
    chapter_title: str = "Chapter 1",
    section_title: str = "Section 1",
    category_code: str | None = None,
    author_name: str | None = None,
) -> tuple[Book, SourceFile, Chapter, Section]:
    source = SourceFile(sha256=sha256, file_path=f"books/{sha256}.pdf", format=SourceFormat.PDF)
    session.add(source)
    session.flush()
    book = Book(source_file_id=source.id, title=title, language=language)
    if category_code:
        category = session.scalar(select(Category).where(Category.code == category_code))
        if category is None:
            category = Category(code=category_code, name=category_code.capitalize())
            session.add(category)
            session.flush()
        book.category_id = category.id
    if author_name:
        author = session.scalar(select(Author).where(Author.name == author_name))
        if author is None:
            author = Author(name=author_name)
            session.add(author)
            session.flush()
        book.author_id = author.id
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, number=1, title=chapter_title, source_file_id=source.id)
    session.add(chapter)
    session.flush()
    section = Section(
        book_id=book.id,
        chapter_id=chapter.id,
        number=1,
        title=section_title,
        source_file_id=source.id,
    )
    session.add(section)
    session.flush()

    page_rows = {}
    for idx, (text, page_no) in enumerate(
        zip(texts, pages or [1] * len(texts), strict=False), start=1
    ):
        if page_no not in page_rows:
            page = Page(
                book_id=book.id,
                source_file_id=source.id,
                page_number=page_no,
                has_text=True,
            )
            session.add(page)
            session.flush()
            page_rows[page_no] = page
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
    session.flush()
    return book, source, chapter, section


def _make_quran(
    session: Session,
    *,
    arabic: str,
    translation_text: str | None = None,
    surah_name: str = "الفاتحة",
) -> tuple[SourceFile, Surah, Ayah]:
    source = SourceFile(sha256="aa" * 32, file_path="quran/aa.pdf", format=SourceFormat.PDF)
    session.add(source)
    surah = Surah(number=1, name_arabic=surah_name, name_en="Al-Fatiha", ayah_count=1)
    session.add(surah)
    session.flush()
    ayah = Ayah(
        surah_id=surah.id,
        source_file_id=source.id,
        number=1,
        text=arabic,
        page_number=1,
        juz=1,
    )
    session.add(ayah)
    session.flush()
    if translation_text is not None:
        session.add(
            Translation(
                ayah_id=ayah.id,
                source_file_id=source.id,
                language="en",
                translator="Test",
                text=translation_text,
            )
        )
    session.flush()
    return source, surah, ayah


def _make_hadith(
    session: Session,
    *,
    text: str,
    text_arabic: str | None = None,
) -> tuple[SourceFile, Collection, Hadith]:
    source = SourceFile(sha256="bb" * 32, file_path="hadith/bb.pdf", format=SourceFormat.PDF)
    session.add(source)
    collection = Collection(name="bukhari", title="Sahih al-Bukhari", author="Al-Bukhari")
    session.add(collection)
    session.flush()
    hadith = Hadith(
        collection_id=collection.id,
        source_file_id=source.id,
        number=1,
        text=text,
        text_arabic=text_arabic,
    )
    session.add(hadith)
    session.flush()
    return source, collection, hadith


def _backfill_vectors(session: Session) -> None:
    """Populate tsvector columns (triggers only exist in migrated databases)."""
    session.execute(
        update(SearchDocument).values(
            search_vector=func.to_tsvector(
                "simple",
                func.concat(func.coalesce(SearchDocument.title, ""), " ", SearchDocument.body_text),
            )
        )
    )
    session.execute(update(Ayah).values(search_vector=func.to_tsvector("simple", Ayah.text)))
    for ayah in session.scalars(select(Ayah)):
        ayah.search_vector_norm = func.to_tsvector("simple", normalize_arabic_search(ayah.text))
    session.execute(
        update(Translation).values(search_vector=func.to_tsvector("simple", Translation.text))
    )
    session.execute(
        update(Hadith).values(
            search_vector=func.to_tsvector(
                "simple",
                func.concat(
                    func.coalesce(Hadith.text, ""), " ", func.coalesce(Hadith.text_arabic, "")
                ),
            )
        )
    )
    session.flush()


def _indexed(session: Session, book: Book, data_dir: Path) -> list[ContentChunk]:
    result = chunk_book(
        book,
        session=session,
        data_dir=data_dir,
        config=ChunkConfig(max_tokens=16, overlap_tokens=0),
    )
    session.flush()
    assert result.error is None
    index_book(book, session=session, data_dir=data_dir)
    session.flush()
    _backfill_vectors(session)
    return session.scalars(
        select(ContentChunk).where(ContentChunk.book_id == book.id).order_by(ContentChunk.sequence)
    ).all()


TEXTS = [
    "The prayer and the fasting are acts of worship.",
    "The sunnah of the Prophet guides our daily habits.",
]


# ------------------------------------------------------------- index stage


def test_index_book_populates_search_documents(db: Session, tmp_path: Path) -> None:
    book, source, _, _ = _make_book(db, "11" * 32, "en", TEXTS, title="Trusted Path")
    chunks = _indexed(db, book, tmp_path)

    docs = db.scalars(
        select(SearchDocument)
        .where(SearchDocument.content_chunk_id.in_([c.id for c in chunks]))
        .order_by(SearchDocument.title)
    ).all()
    assert len(docs) == len(chunks)
    for doc in docs:
        assert doc.document_type == "chunk"
        assert doc.language == Language.ENGLISH
        assert doc.title == "Trusted Path"
        assert doc.body_text

    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.INDEX,
        )
    ).one()
    assert job.status == JobStatus.SUCCEEDED
    assert job.manifest["document_count"] == len(chunks)
    assert job.manifest["chunk_count"] == len(chunks)

    report = tmp_path / "processed" / "index" / f"{'11' * 32}.txt"
    assert report.is_file()


def test_index_book_idempotent(db: Session, tmp_path: Path) -> None:
    book, source, _, _ = _make_book(db, "22" * 32, "en", TEXTS)
    chunks1 = _indexed(db, book, tmp_path)
    db.expire_all()

    result = index_book(book, session=db, data_dir=tmp_path)
    db.flush()
    db.expire_all()

    assert result.error is None
    assert result.document_count == len(chunks1)
    count = db.scalar(
        select(func.count())
        .select_from(SearchDocument)
        .where(SearchDocument.content_chunk_id.in_([c.id for c in chunks1]))
    )
    assert count == len(chunks1)


def test_index_book_no_chunks_failed_job(db: Session, tmp_path: Path) -> None:
    book, source, _, _ = _make_book(db, "33" * 32, "en", [])
    result = index_book(book, session=db, data_dir=tmp_path)
    db.flush()

    assert result.error is not None
    assert "no chunks" in result.error
    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.INDEX,
        )
    ).one()
    assert job.status == JobStatus.FAILED
    assert job.error == result.error
    assert job.manifest["document_count"] == 0


# ----------------------------------------------------------------- searches


def test_search_keyword_content_with_provenance(db: Session, tmp_path: Path) -> None:
    book, source, chapter, section = _make_book(db, "44" * 32, "en", TEXTS)
    _indexed(db, book, tmp_path)

    hits = search(db, SearchParams(query="prayer", domains=("content",)))
    assert hits
    hit = hits[0]
    assert hit.domain == "content"
    assert "prayer" in hit.matched_text.lower()
    assert hit.book == "Search Fixture"
    assert hit.language == "en"
    assert hit.book_id.startswith(str(book.id)[:8])
    assert hit.chapter_id == str(chapter.id)
    assert hit.section_id == str(section.id)
    assert hit.source_file_id == str(source.id)
    assert hit.chunk_id
    assert hit.page is not None


def test_search_exact_phrase(db: Session, tmp_path: Path) -> None:
    book, _, _, _ = _make_book(db, "45" * 32, "en", TEXTS)
    _indexed(db, book, tmp_path)

    phrase = search(db, SearchParams(query='"daily habits"', domains=("content",)))
    assert phrase and "daily habits" in phrase[0].matched_text.lower()

    broken = search(db, SearchParams(query='"habits daily"', domains=("content",)))
    assert not broken


def test_search_multi_term_any_and_all(db: Session, tmp_path: Path) -> None:
    book, _, _, _ = _make_book(db, "46" * 32, "en", TEXTS)
    _indexed(db, book, tmp_path)

    any_term = search(db, SearchParams(query="prayer sunnah", domains=("content",)))
    assert len(any_term) == 2  # each chunk matches one keyword

    both = search(db, SearchParams(query="prayer worship", domains=("content",)))
    assert both and "worship" in both[0].matched_text.lower()

    none = search(db, SearchParams(query="prayer sunnah", all_terms=True, domains=("content",)))
    assert not none  # no single chunk contains both words


def test_search_book_chapter_section_domains(db: Session, tmp_path: Path) -> None:
    book, _, _, _ = _make_book(
        db,
        "47" * 32,
        "en",
        ["Body text."],
        title="Riyad as-Salihin",
        chapter_title="On Prayer",
        section_title="Evening Remembrances",
    )
    _indexed(db, book, tmp_path)

    books = search(db, SearchParams(query="riyad", domains=("book",)))
    assert books and books[0].domain == "book" and books[0].book == "Riyad as-Salihin"

    chapters = search(db, SearchParams(query="prayer", domains=("chapter",)))
    assert chapters and chapters[0].domain == "chapter"
    assert chapters[0].chapter == "On Prayer"

    sections = search(db, SearchParams(query="remembrances", domains=("section",)))
    assert sections and sections[0].domain == "section"
    assert sections[0].section == "Evening Remembrances"


def test_search_filters(db: Session, tmp_path: Path) -> None:
    book, source, _, _ = _make_book(
        db,
        "48" * 32,
        "en",
        TEXTS,
        title="Fiqh of Worship",
        category_code="fiqh",
        author_name="Al-Ghazali",
    )
    other, _, _, _ = _make_book(db, "49" * 32, "ar", TEXTS, title="متن آخر")
    _indexed(db, book, tmp_path)
    _indexed(db, other, tmp_path)

    by_category = search(db, SearchParams(query="prayer", domains=("content",), category="fiqh"))
    assert by_category and all(h.book == "Fiqh of Worship" for h in by_category)

    by_author = search(db, SearchParams(query="prayer", domains=("content",), author="al-ghazali"))
    assert by_author and by_author[0].author == "Al-Ghazali"

    by_language = search(db, SearchParams(query="prayer", domains=("content",), language="en"))
    assert by_language and all(h.language == "en" for h in by_language)

    by_source = search(db, SearchParams(query="prayer", domains=("content",), source="48" * 8))
    assert by_source and all(h.source_file_id == str(source.id) for h in by_source)

    by_domain = search(db, SearchParams(query="riyad", domains=("book",)))
    assert not any(h.domain == "content" for h in by_domain)


def test_search_quran_arabic(db: Session, tmp_path: Path) -> None:
    arabic = "بسم الله الرحمن الرحيم"
    _make_quran(db, arabic=arabic)
    _backfill_vectors(db)

    hits = search(db, SearchParams(query="بسم الله", domains=("quran",)))
    assert hits
    assert hits[0].domain == "quran"
    assert "بسم الله" in hits[0].matched_text
    assert hits[0].citation == "1:1"
    assert hits[0].language == "ar"


def test_search_quran_translation(db: Session, tmp_path: Path) -> None:
    _make_quran(db, arabic="سبحان", translation_text="Glory be to God")
    _backfill_vectors(db)

    hits = search(db, SearchParams(query="glory", domains=("quran",), language="en"))
    assert hits
    assert hits[0].language == "en"
    assert "Glory" in hits[0].matched_text
    assert "Test" in hits[0].citation


def test_search_quran_modern_arabic_matches_diacritics(db: Session, tmp_path: Path) -> None:
    # Qur'anic orthography: alef-wasla, superscript alef, full tashkeel.
    _make_quran(db, arabic="ٱلرَّحْمَٰنِ ٱلرَّحِيمِ")
    _backfill_vectors(db)

    plain = search(db, SearchParams(query="الرحمن", domains=("quran",)))
    assert plain
    assert plain[0].domain == "quran"
    assert plain[0].citation == "1:1"

    diacritics = search(db, SearchParams(query="ٱلرَّحْمَٰنِ", domains=("quran",)))
    assert diacritics
    assert diacritics[0].citation == "1:1"

    unrelated = search(db, SearchParams(query="القرآن", domains=("quran",)))
    assert not unrelated


def test_search_hadith_text_and_arabic(db: Session, tmp_path: Path) -> None:
    _make_hadith(db, text="Actions are by intentions", text_arabic="إنما الأعمال بالنيات")
    _backfill_vectors(db)

    en = search(db, SearchParams(query="intentions", domains=("hadith",)))
    assert en and en[0].domain == "hadith"
    assert en[0].book == "Sahih al-Bukhari"
    assert "by intentions" in en[0].matched_text.lower()

    ar = search(db, SearchParams(query="بالنيات", domains=("hadith",), language="ar"))
    assert ar and "بالنيات" in ar[0].matched_text


def test_search_empty_and_blank(db: Session, tmp_path: Path) -> None:
    book, _, _, _ = _make_book(db, "50" * 32, "en", TEXTS)
    _indexed(db, book, tmp_path)

    assert search(db, SearchParams(query="")) == []
    assert search(db, SearchParams(query="   ")) == []


def test_search_result_limit(db: Session, tmp_path: Path) -> None:
    book, _, _, _ = _make_book(db, "51" * 32, "en", TEXTS)
    _indexed(db, book, tmp_path)

    hits = search(db, SearchParams(query="prayer sunnah", domains=("content",), limit=1))
    assert len(hits) == 1
    hits2 = search(db, SearchParams(query="prayer sunnah", domains=("content",), limit=5))
    assert len(hits2) == 2
