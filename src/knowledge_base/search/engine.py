"""Full-text search engine over the knowledge base.

Domain backends:

* ``book`` / ``chapter`` / ``section`` — trigram (``pg_trgm``) substring
  matches on catalog titles/names, ranked by similarity;
* ``content`` — PostgreSQL ``tsvector`` full-text search over indexed chunk
  documents (``search_documents``), returning full book/chapter/page
  provenance and a ``ts_headline`` snippet;
* ``quran`` — tsvector over ayahs (Arabic) and ayah translations;
* ``hadith`` — tsvector over hadith English text + Arabic original.

Every document vector carries a verbatim ``simple`` component, so queries are
always built with the ``simple`` configuration after language-aware query
normalization; matching and ranking are done entirely inside PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import Language
from knowledge_base.database.models.books import Author, Book, Category
from knowledge_base.database.models.hadith import Collection, Hadith, HadithBook, HadithChapter
from knowledge_base.database.models.quran import Ayah, Surah, Translation
from knowledge_base.database.models.search import SearchDocument
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.database.models.structure import Chapter, ContentChunk, Section
from knowledge_base.search.hits import SearchHit
from knowledge_base.search.queries import build_websearch

_ALL_DOMAINS = ("book", "chapter", "section", "content", "quran", "hadith")

_HEADLINE = "StartSel=<mark>, StopSel=</mark>, MaxWords=24, MinWords=6, MaxFragments=2"

# Book.language is a free-form string in the catalog; map CLI filters onto the
# aliases the metadata stage may have stored (e.g. "ar", "ara", "arabic").
_BOOK_LANG_ALIASES = {
    "ar": ("ar", "ara", "arabic"),
    "ur": ("ur", "urd", "urdu"),
    "en": ("en", "eng", "english"),
}


@dataclass
class SearchParams:
    """Everything a full-text search can be scoped by."""

    query: str
    domains: tuple[str, ...] = _ALL_DOMAINS
    all_terms: bool = False
    language: str | None = None
    category: str | None = None
    source: str | None = None
    author: str | None = None
    limit: int = 20
    _websearch: str = field(init=False, repr=False, default="")


def _tzs(web: str) -> Any:
    """tsquery expression built with the universal ``simple`` config."""
    return func.websearch_to_tsquery("simple", web)


def _ts_rank(vector: Any, tq: Any) -> Any:
    return func.ts_rank_cd(vector, tq)


def _headline(body: Any, tq: Any) -> Any:
    return func.ts_headline("simple", body, tq, _HEADLINE)


def _lang_filter(column: Any, lang: str) -> list[Any]:
    if lang in _BOOK_LANG_ALIASES:
        aliases = _BOOK_LANG_ALIASES[lang]
        return [func.lower(func.coalesce(column, "")).in_(aliases)]
    return []


def _tsvector_col(column: Any, lang: str) -> list[Any]:
    """Full enum value match for tsvector-backed columns (search_documents)."""
    if lang in {Language.ARABIC.value, Language.URDU.value, Language.ENGLISH.value, "other"}:
        return [column == Language(lang)]
    return []


def _sha_prefix_filter(source: str | None) -> list[Any]:
    return [SourceFile.sha256.startswith(source)] if source else []


def _book_scope(
    book: Any,
    language: str | None = None,
    category: str | None = None,
    source: str | None = None,
    author: str | None = None,
) -> list[Any]:
    """Filters shared by catalog/content domains that resolve to a Book."""
    clauses: list[Any] = []
    if language:
        clauses.extend(_lang_filter(book.language, language))
    if category:
        clauses.append(Category.code == category)
    if source:
        clauses.append(SourceFile.sha256.startswith(source))
    if author:
        clauses.append(Author.name.ilike(f"%{author}%"))
    return clauses


def _search_content(session: Session, params: SearchParams, tq: Any) -> list[SearchHit]:
    rank = _ts_rank(SearchDocument.search_vector, tq)
    rows = session.execute(
        select(
            SearchDocument,
            ContentChunk,
            Book,
            Chapter,
            Section,
            SourceFile,
            rank,
            _headline(SearchDocument.body_text, tq),
        )
        .join(ContentChunk, SearchDocument.content_chunk_id == ContentChunk.id)
        .join(Book, ContentChunk.book_id == Book.id)
        .join(SourceFile, Book.source_file_id == SourceFile.id)
        .outerjoin(Author, Book.author_id == Author.id)
        .outerjoin(Category, Book.category_id == Category.id)
        .outerjoin(Chapter, ContentChunk.chapter_id == Chapter.id)
        .outerjoin(Section, ContentChunk.section_id == Section.id)
        .where(
            SearchDocument.search_vector.op("@@")(tq),
            *_tsvector_col(SearchDocument.language, params.language or ""),
            *_book_scope(
                Book,
                category=params.category,
                source=params.source,
                author=params.author,
            ),
        )
        .order_by(rank.desc())
        .limit(params.limit)
    ).all()

    hits: list[SearchHit] = []
    for sd, chunk, book, chapter, section, sf, r, snippet in rows:
        hits.append(
            SearchHit(
                domain="content",
                rank=float(r or 0.0),
                title=book.title,
                matched_text=sd.body_text,
                snippet=snippet or "",
                language=sd.language.value,
                book=book.title,
                author=book.author.name if book.author else None,
                category=book.category.code if book.category else None,
                chapter=chapter.title if chapter else None,
                section=section.title if section else None,
                page=chunk.page_start or chunk.page_end,
                citation=chunk.chunk_id,
                book_id=str(book.id),
                chapter_id=str(chapter.id) if chapter else None,
                section_id=str(section.id) if section else None,
                source_file_id=str(sf.id),
                chunk_id=chunk.chunk_id,
            )
        )
    return hits


def _search_book(session: Session, params: SearchParams) -> list[SearchHit]:
    q = params.query
    like = f"%{q.lower()}%"
    rank = func.greatest(
        func.similarity(func.lower(Book.title), q),
        func.coalesce(func.similarity(func.lower(func.coalesce(Book.subtitle, "")), q), 0),
        func.coalesce(func.similarity(func.lower(func.coalesce(Author.name, "")), q), 0),
    )
    stmt = (
        select(Book, SourceFile, rank)
        .outerjoin(Author, Book.author_id == Author.id)
        .outerjoin(Category, Book.category_id == Category.id)
        .join(SourceFile, Book.source_file_id == SourceFile.id)
        .where(
            func.lower(Book.title).like(like)
            | func.lower(func.coalesce(Book.subtitle, "")).like(like)
            | func.lower(func.coalesce(Author.name, "")).like(like),
            *_book_scope(Book, params.language, params.category, params.source, params.author),
        )
        .order_by(rank.desc())
        .limit(params.limit)
    )
    hits: list[SearchHit] = []
    for book, sf, r in session.execute(stmt).all():
        hits.append(
            SearchHit(
                domain="book",
                rank=float(r or 0.0),
                title=book.title,
                matched_text=book.title,
                snippet="",
                language=(book.language or "").lower(),
                book=book.title,
                author=book.author.name if book.author else None,
                category=book.category.code if book.category else None,
                book_id=str(book.id),
                source_file_id=str(sf.id),
                source_sha256=sf.sha256,
            )
        )
    return hits


def _search_chapter(session: Session, params: SearchParams) -> list[SearchHit]:
    like = f"%{params.query.lower()}%"
    q = params.query
    rank = func.similarity(func.lower(Chapter.title), q)
    stmt = (
        select(Chapter, Book, SourceFile, rank)
        .join(Book, Chapter.book_id == Book.id)
        .join(SourceFile, Book.source_file_id == SourceFile.id)
        .outerjoin(Category, Book.category_id == Category.id)
        .outerjoin(Author, Book.author_id == Author.id)
        .where(
            func.lower(Chapter.title).like(like),
            *_book_scope(Book, params.language, params.category, params.source, params.author),
        )
        .order_by(rank.desc())
        .limit(params.limit)
    )
    hits: list[SearchHit] = []
    for chapter, book, sf, r in session.execute(stmt).all():
        hits.append(
            SearchHit(
                domain="chapter",
                rank=float(r or 0.0),
                title=book.title,
                matched_text=chapter.title,
                snippet="",
                language=(book.language or "").lower(),
                book=book.title,
                author=book.author.name if book.author else None,
                category=book.category.code if book.category else None,
                chapter=chapter.title,
                book_id=str(book.id),
                chapter_id=str(chapter.id),
                source_file_id=str(sf.id),
            )
        )
    return hits


def _search_section(session: Session, params: SearchParams) -> list[SearchHit]:
    like = f"%{params.query.lower()}%"
    q = params.query
    rank = func.similarity(func.lower(Section.title), q)
    stmt = (
        select(Section, Chapter, Book, SourceFile, rank)
        .join(Chapter, Section.chapter_id == Chapter.id)
        .join(Book, Section.book_id == Book.id)
        .join(SourceFile, Book.source_file_id == SourceFile.id)
        .outerjoin(Category, Book.category_id == Category.id)
        .outerjoin(Author, Book.author_id == Author.id)
        .where(
            func.lower(Section.title).like(like),
            *_book_scope(Book, params.language, params.category, params.source, params.author),
        )
        .order_by(rank.desc())
        .limit(params.limit)
    )
    hits: list[SearchHit] = []
    for section, chapter, book, sf, r in session.execute(stmt).all():
        hits.append(
            SearchHit(
                domain="section",
                rank=float(r or 0.0),
                title=book.title,
                matched_text=section.title,
                snippet="",
                language=(book.language or "").lower(),
                book=book.title,
                author=book.author.name if book.author else None,
                category=book.category.code if book.category else None,
                chapter=chapter.title,
                section=section.title,
                book_id=str(book.id),
                chapter_id=str(chapter.id),
                section_id=str(section.id),
                source_file_id=str(sf.id),
            )
        )
    return hits


def _search_quran(session: Session, params: SearchParams, tq: Any) -> list[SearchHit]:
    lang = params.language
    hits: list[SearchHit] = []

    if lang in (None, "ar", "other"):
        rank = _ts_rank(func.coalesce(Ayah.search_vector_norm, Ayah.search_vector), tq)
        rows = session.execute(
            select(Ayah, Surah, SourceFile, rank, _headline(Ayah.text, tq))
            .join(Surah, Ayah.surah_id == Surah.id)
            .join(SourceFile, Ayah.source_file_id == SourceFile.id)
            .where(
                func.coalesce(Ayah.search_vector_norm, Ayah.search_vector).op("@@")(tq),
                *_sha_prefix_filter(params.source),
            )
            .order_by(rank.desc())
            .limit(params.limit)
        ).all()
        for ayah, surah, sf, r, snippet in rows:
            hits.append(
                SearchHit(
                    domain="quran",
                    rank=float(r or 0.0),
                    title="Quran",
                    matched_text=ayah.text,
                    snippet=snippet or "",
                    language="ar",
                    book="Quran",
                    chapter=surah.name_arabic,
                    page=ayah.page_number,
                    citation=f"{surah.number}:{ayah.number}",
                    source_file_id=str(sf.id),
                )
            )

    if lang in (None, "en", "ur", "other"):
        trank = _ts_rank(Translation.search_vector, tq)
        clauses: list[Any] = [Translation.search_vector.op("@@")(tq)]
        if lang and lang not in ("ar", "other"):
            clauses.append(Translation.language == lang)
        clauses.extend(_sha_prefix_filter(params.source))
        trows = session.execute(
            select(Translation, Ayah, Surah, SourceFile, trank, _headline(Translation.text, tq))
            .join(Ayah, Translation.ayah_id == Ayah.id)
            .join(Surah, Ayah.surah_id == Surah.id)
            .join(SourceFile, Translation.source_file_id == SourceFile.id)
            .where(*clauses)
            .order_by(trank.desc())
            .limit(params.limit)
        ).all()
        for trans, ayah, surah, sf, r, snippet in trows:
            hits.append(
                SearchHit(
                    domain="quran",
                    rank=float(r or 0.0),
                    title="Quran",
                    matched_text=trans.text,
                    snippet=snippet or "",
                    language=trans.language.lower(),
                    book="Quran",
                    chapter=surah.name_arabic,
                    page=ayah.page_number,
                    citation=f"{surah.number}:{ayah.number} ({trans.translator})",
                    source_file_id=str(sf.id),
                )
            )
    return hits


def _search_hadith(session: Session, params: SearchParams, tq: Any) -> list[SearchHit]:
    combined = func.concat(
        func.coalesce(Hadith.text, ""), " ", func.coalesce(Hadith.text_arabic, "")
    )
    rank = _ts_rank(Hadith.search_vector, tq)
    rows = session.execute(
        select(
            Hadith,
            Collection,
            HadithBook,
            HadithChapter,
            SourceFile,
            rank,
            _headline(combined, tq),
        )
        .join(Collection, Hadith.collection_id == Collection.id)
        .outerjoin(HadithBook, Hadith.hadith_book_id == HadithBook.id)
        .outerjoin(HadithChapter, Hadith.hadith_chapter_id == HadithChapter.id)
        .join(SourceFile, Hadith.source_file_id == SourceFile.id)
        .where(
            Hadith.search_vector.op("@@")(tq),
            *_sha_prefix_filter(params.source),
        )
        .order_by(rank.desc())
        .limit(params.limit)
    ).all()
    hits: list[SearchHit] = []
    for hadith, coll, hbook, hchapter, sf, r, snippet in rows:
        use_arabic = params.language == "ar" and bool(hadith.text_arabic)
        hits.append(
            SearchHit(
                domain="hadith",
                rank=float(r or 0.0),
                title=coll.title or coll.name,
                matched_text=hadith.text_arabic if use_arabic else (hadith.text or ""),
                snippet=snippet or "",
                language="ar" if use_arabic else "en",
                book=coll.title or coll.name,
                author=coll.author,
                chapter=hchapter.name if hchapter else None,
                section=hbook.name if hbook else None,
                citation=f"{coll.name} #{hadith.number}",
                source_file_id=str(sf.id),
            )
        )
    return hits


def search(session: Session, params: SearchParams) -> list[SearchHit]:
    """Run a full-text search; results are ranked across all requested domains."""
    web = build_websearch(params.query, all_terms=params.all_terms)
    params._websearch = web
    if not web:
        return []

    tq = _tzs(web)
    collected: list[SearchHit] = []
    if "content" in params.domains:
        collected.extend(_search_content(session, params, tq))
    if "book" in params.domains:
        collected.extend(_search_book(session, params))
    if "chapter" in params.domains:
        collected.extend(_search_chapter(session, params))
    if "section" in params.domains:
        collected.extend(_search_section(session, params))
    if "quran" in params.domains:
        collected.extend(_search_quran(session, params, tq))
    if "hadith" in params.domains:
        collected.extend(_search_hadith(session, params, tq))

    collected.sort(key=lambda h: h.rank, reverse=True)
    return collected[: params.limit]


__all__ = ["SearchParams", "search"]
