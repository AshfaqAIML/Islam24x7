"""Tests for semantic (vector) search.

Covers the ``similar`` API: cosine-similarity ranking, full source provenance
on every hit, embedding-model scoping, empty queries, dimension mismatch, and
each metadata filter (category, book/source, language, source-type, author,
minimum score). The deterministic dummy provider keeps embedding reproducible
in-process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import BlockType, SourceFormat
from knowledge_base.database.models.books import Author, Book, Category
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Page,
    Section,
)
from knowledge_base.pipeline.chunk.config import ChunkConfig
from knowledge_base.pipeline.chunk.processor import chunk_book
from knowledge_base.pipeline.embed.config import EmbedConfig
from knowledge_base.pipeline.embed.processor import embed_book
from knowledge_base.pipeline.embed.provider import DummyEmbeddingProvider
from knowledge_base.search import similar

DIMS = 768

TEXTS = [
    "importance of patience and sabr when facing hardship and trials",
    "the structural engineering of suspension bridges and cable forces",
]


def _config(**overrides) -> EmbedConfig:
    defaults = dict(
        model_name="kb-vec",
        model_version="0.1.0",
        dimensions=DIMS,
        batch_size=16,
        max_retries=2,
        backoff_seconds=0.0,
    )
    defaults.update(overrides)
    return EmbedConfig(**defaults)


def _provider(config: EmbedConfig) -> DummyEmbeddingProvider:
    return DummyEmbeddingProvider(dimensions=config.dimensions)


def _make_book(
    session: Session,
    sha256: str,
    texts: list[str],
    *,
    title: str = "Vector Fixture",
    language: str = "en",
    category_code: str | None = None,
    author_name: str | None = None,
    fmt: SourceFormat = SourceFormat.PDF,
) -> tuple[Book, SourceFile]:
    source = SourceFile(
        sha256=sha256, file_path=f"books/{sha256}.{fmt.value}", format=fmt
    )
    session.add(source)
    session.flush()
    author = None
    if author_name:
        author = Author(name=author_name)
        session.add(author)
        session.flush()
    category = None
    if category_code:
        category = Category(code=category_code, name=category_code)
        session.add(category)
        session.flush()
    book = Book(
        source_file_id=source.id,
        title=title,
        language=language,
        author_id=author.id if author else None,
        category_id=category.id if category else None,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id, number=1, title="Chapter 1", source_file_id=source.id
    )
    session.add(chapter)
    session.flush()
    session.add(
        Section(
            book_id=book.id, chapter_id=chapter.id, number=1, title="Section 1",
            source_file_id=source.id,
        )
    )
    page = Page(book_id=book.id, source_file_id=source.id, page_number=1, has_text=True)
    session.add(page)
    session.flush()
    for idx, text in enumerate(texts, start=1):
        session.add(
            ContentBlock(
                book_id=book.id,
                page_id=page.id,
                chapter_id=chapter.id,
                source_file_id=source.id,
                block_type=BlockType.PARAGRAPH,
                sequence=idx,
                original_text=text,
            )
        )
    session.flush()
    return book, source


def _chunked(session: Session, book: Book, data_dir: Path) -> list[ContentChunk]:
    result = chunk_book(
        book, session=session, data_dir=data_dir,
        config=ChunkConfig(max_tokens=16, overlap_tokens=0),
    )
    session.flush()
    assert result.error is None
    return list(
        session.scalars(
            select(ContentChunk)
            .where(ContentChunk.book_id == book.id)
            .order_by(ContentChunk.sequence)
        )
    )


def _embedded(
    session: Session, book: Book, data_dir: Path, config: EmbedConfig
) -> list[ContentChunk]:
    chunks = _chunked(session, book, data_dir)
    result = embed_book(
        book, session=session, data_dir=data_dir,
        provider=_provider(config), config=config,
    )
    session.expire_all()
    assert result.error is None
    return chunks


def test_similar_ranks_by_relevance_and_keeps_provenance(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, source = _make_book(db, "21" * 32, TEXTS)
    chunks = _embedded(db, book, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, model_version=config.model_version,
    )
    assert len(hits) == 2
    assert hits[0].score > hits[1].score
    assert hits[0].text == TEXTS[0]
    assert hits[0].chunk_id == chunks[0].chunk_id
    assert hits[0].score > 0.9

    hit = hits[0]
    assert hit.content_id == str(chunks[0].id)
    assert hit.book == "Vector Fixture"
    assert hit.book_id == str(book.id)
    assert hit.chapter == "Chapter 1"
    assert hit.chapter_id == str(chunks[0].chapter_id)
    assert hit.page == 1
    assert hit.language == "en"
    assert hit.source == source.sha256
    assert hit.source_id == str(source.id)
    assert hit.source_type == "pdf"


def test_similar_empty_query_returns_nothing(db: Session, tmp_path: Path) -> None:
    config = _config()
    book, _ = _make_book(db, "22" * 32, TEXTS)
    _embedded(db, book, tmp_path, config)

    assert similar(db, "", _provider(config), model_name=config.model_name) == []
    assert similar(db, "   ", _provider(config), model_name=config.model_name) == []


def test_similar_unknown_model_returns_nothing(db: Session) -> None:
    config = _config()
    assert similar(
        db, "patience", _provider(config), model_name="does-not-exist"
    ) == []


def test_similar_scopes_to_model_version(db: Session, tmp_path: Path) -> None:
    config = _config()
    book, _ = _make_book(db, "23" * 32, TEXTS)
    _embedded(db, book, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, model_version="0.2.0",
    )
    assert hits == []
    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name,
    )
    assert len(hits) == 2


def test_similar_model_version_omitted_uses_latest(
    db: Session, tmp_path: Path
) -> None:
    book_a, _ = _make_book(db, "24" * 32, TEXTS)
    _embedded(db, book_a, tmp_path, _config())
    book_b, _ = _make_book(db, "99" * 32, TEXTS)
    _embedded(db, book_b, tmp_path, _config(model_version="0.2.0"))

    provider = _provider(_config())
    latest = similar(db, TEXTS[0], provider, model_name="kb-vec")
    old = similar(
        db, TEXTS[0], provider,
        model_name="kb-vec", model_version="0.1.0",
    )
    assert len(latest) == len(old) == 2
    assert {h.book_id for h in latest} == {str(book_b.id)}
    assert {h.book_id for h in old} == {str(book_a.id)}


def test_similar_provider_dimension_mismatch_raises(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, _ = _make_book(db, "25" * 32, TEXTS)
    _embedded(db, book, tmp_path, config)

    bad = DummyEmbeddingProvider(dimensions=32)
    with pytest.raises(ValueError, match="do not match model"):
        similar(db, "patience", bad, model_name=config.model_name)


def test_similar_min_score_filters_low_scoring_hits(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, _ = _make_book(db, "26" * 32, TEXTS)
    _embedded(db, book, tmp_path, config)

    best = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, min_score=0.95,
    )
    assert len(best) == 1
    assert best[0].text == TEXTS[0]


def test_similar_category_filter(db: Session, tmp_path: Path) -> None:
    config = _config()
    book_a, _ = _make_book(
        db, "30" * 32, TEXTS, category_code="tafsir", title="Book A"
    )
    book_b, _ = _make_book(
        db, "31" * 32, TEXTS, category_code="fiqh", title="Book B"
    )
    _embedded(db, book_a, tmp_path, config)
    _embedded(db, book_b, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, category="fiqh",
    )
    assert hits and all(h.book == "Book B" for h in hits)


def test_similar_book_source_filter(db: Session, tmp_path: Path) -> None:
    config = _config()
    book_a, sf_a = _make_book(db, "32" * 32, TEXTS, title="Book A")
    book_b, _ = _make_book(db, "33" * 32, TEXTS, title="Book B")
    _embedded(db, book_a, tmp_path, config)
    _embedded(db, book_b, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, source=sf_a.sha256[:12],
    )
    assert hits and all(h.book == "Book A" for h in hits)


def test_similar_language_filter(db: Session, tmp_path: Path) -> None:
    config = _config()
    book_en, _ = _make_book(db, "34" * 32, TEXTS, title="English", language="en")
    book_ur, _ = _make_book(
        db, "35" * 32, TEXTS, title="Urdu", language="ur",
    )
    _embedded(db, book_en, tmp_path, config)
    _embedded(db, book_ur, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, language="en",
    )
    assert hits and all(h.book == "English" for h in hits)


def test_similar_source_type_filter(db: Session, tmp_path: Path) -> None:
    config = _config()
    book_pdf, _ = _make_book(db, "36" * 32, TEXTS, title="PDF", fmt=SourceFormat.PDF)
    book_epub, _ = _make_book(db, "37" * 32, TEXTS, title="EPUB", fmt=SourceFormat.EPUB)
    _embedded(db, book_pdf, tmp_path, config)
    _embedded(db, book_epub, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, source_type="epub",
    )
    assert hits and all(h.book == "EPUB" for h in hits)


def test_similar_author_filter(db: Session, tmp_path: Path) -> None:
    config = _config()
    book_a, _ = _make_book(db, "38" * 32, TEXTS, title="Authored", author_name="Ibn Khaldun")
    other, _ = _make_book(db, "39" * 32, TEXTS, title="Anonymous")
    _embedded(db, book_a, tmp_path, config)
    _embedded(db, other, tmp_path, config)

    hits = similar(
        db, TEXTS[0], _provider(config),
        model_name=config.model_name, author="khaldun",
    )
    assert hits and all(h.book == "Authored" for h in hits)
    assert hits[0].author == "Ibn Khaldun"


def test_similar_hits_trace_back_to_source_file(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, source = _make_book(db, "40" * 32, TEXTS)
    chunks = _embedded(db, book, tmp_path, config)

    hits = similar(
        db, TEXTS[1], _provider(config),
        model_name=config.model_name,
    )
    hit = next(h for h in hits if h.chunk_id == chunks[1].chunk_id)

    stored = db.get(ContentChunk, chunks[1].id)
    stored_sf = db.get(SourceFile, source.id)
    assert hit.source == stored_sf.sha256
    assert hit.chunk_id == stored.chunk_id
    assert hit.content_id == str(stored.id)