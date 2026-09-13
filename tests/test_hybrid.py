"""Tests for hybrid (keyword + semantic) retrieval.

Uses representative Islamic queries. The evaluation checks that hybrid search
(i) finds passages whose exact keywords are absent via the semantic path —
e.g. "importance of patience" surfacing a "sabr / perseverance / forgiveness"
passage, (ii) still works keyword-only without embeddings, (iii) fuses and
deduplicates the two retrievers, (iv) honours configurable weighting, and
(v) never loses source provenance.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from knowledge_base.database.enums import BlockType, SourceFormat
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.search import SearchDocument
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
from knowledge_base.pipeline.index.index import index_book
from knowledge_base.search import hybrid_search

DIMS = 768

PATIENCE = "importance of patience when facing hardship"
SABR = "the believer shows perseverance sabr self-control and forgiveness during tribulations"


def _config(**overrides) -> EmbedConfig:
    defaults = dict(
        model_name="kb-hyb",
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
    session: Session, sha256: str, texts: list[str], *, title: str = "Hybrid Fixture"
) -> tuple[Book, SourceFile]:
    source = SourceFile(sha256=sha256, file_path=f"books/{sha256}.pdf", format=SourceFormat.PDF)
    session.add(source)
    session.flush()
    book = Book(source_file_id=source.id, title=title, language="en")
    session.add(book)
    session.flush()
    chapter = Chapter(book_id=book.id, number=1, title="Chapter 1", source_file_id=source.id)
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


def _prepared(
    session: Session, book: Book, data_dir: Path, config: EmbedConfig
) -> list[ContentChunk]:
    result = chunk_book(
        book, session=session, data_dir=data_dir,
        config=ChunkConfig(max_tokens=16, overlap_tokens=0),
    )
    session.flush()
    assert result.error is None
    idx = index_book(book, session=session, data_dir=data_dir)
    session.flush()
    assert idx.error is None
    session.execute(
        update(SearchDocument).values(
            search_vector=func.to_tsvector(
                "simple",
                func.concat(
                    func.coalesce(SearchDocument.title, ""), " ",
                    SearchDocument.body_text,
                ),
            )
        )
    )
    session.flush()
    emb = embed_book(
        book, session=session, data_dir=data_dir,
        provider=_provider(config), config=config,
    )
    session.expire_all()
    assert emb.error is None
    return list(
        session.scalars(
            select(ContentChunk)
            .where(ContentChunk.book_id == book.id)
            .order_by(ContentChunk.sequence)
        )
    )


def test_hybrid_fuses_and_dedups_both_retrievers(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, _ = _make_book(db, "51" * 32, [PATIENCE, SABR])
    chunks = _prepared(db, book, tmp_path, config)

    hits = hybrid_search(
        db, PATIENCE, provider=_provider(config),
        model_name=config.model_name, model_version=config.model_version,
    )
    matched = [h for h in hits if h.chunk_id == chunks[0].chunk_id]
    assert len(matched) == 1  # deduplicated across retrievers
    hit = matched[0]
    assert "fts" in hit.retrievers
    assert "vector" in hit.retrievers
    assert hit.fts_score is not None and hit.fts_score > 0
    assert hit.vector_score is not None and hit.vector_score > 0
    assert hit.book == "Hybrid Fixture"
    assert hit.chapter == "Chapter 1"
    assert hit.page == 1
    assert hit.source == "51" * 32
    assert hit.content_id is not None


def test_hybrid_finds_passage_without_exact_keywords(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book_sabr, _ = _make_book(db, "52" * 32, [SABR], title="Sabr Treatise")
    chunks = _prepared(db, book_sabr, tmp_path, config)

    keyword_only = hybrid_search(
        db, PATIENCE, provider=None,
        model_name=config.model_name, weight_vector=0.0,
    )
    assert all(h.chunk_id != chunks[0].chunk_id for h in keyword_only)

    blended = hybrid_search(
        db, PATIENCE, provider=_provider(config),
        model_name=config.model_name, model_version=config.model_version,
    )
    assert any(h.chunk_id == chunks[0].chunk_id for h in blended)
    via_vector = next(h for h in blended if h.chunk_id == chunks[0].chunk_id)
    assert "vector" in via_vector.retrievers
    assert via_vector.vector_score is not None and via_vector.vector_score > 0


def test_hybrid_keyword_only_without_embeddings(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, _ = _make_book(db, "53" * 32, [PATIENCE, SABR])
    chunks = _prepared(db, book, tmp_path, config)

    hits = hybrid_search(
        db, PATIENCE, provider=None,
        model_name=config.model_name, weight_vector=0.0,
    )
    assert hits
    assert all(h.chunk_id == chunks[0].chunk_id for h in hits)
    assert all("fts" in h.retrievers for h in hits)
    assert all(h.vector_score is None for h in hits)


def test_hybrid_weighting_selects_retrieval_path(
    db: Session, tmp_path: Path
) -> None:
    config = _config()
    book, _ = _make_book(db, "54" * 32, [PATIENCE, SABR])
    chunks = _prepared(db, book, tmp_path, config)

    kw = hybrid_search(
        db, PATIENCE, provider=_provider(config),
        model_name=config.model_name, weight_vector=0.0, weight_fts=1.0,
    )
    sem = hybrid_search(
        db, PATIENCE, provider=_provider(config),
        model_name=config.model_name, weight_fts=0.0, weight_vector=1.0,
    )
    kw_ids = {h.chunk_id for h in kw}
    sem_ids = {h.chunk_id for h in sem}
    assert chunks[0].chunk_id in kw_ids
    assert chunks[1].chunk_id in sem_ids
    assert sem_ids - kw_ids  # semantic path alone surfaces the sabr passage


def test_hybrid_preserves_source_provenance(db: Session, tmp_path: Path) -> None:
    config = _config()
    book, source = _make_book(db, "55" * 32, [PATIENCE, SABR])
    chunks = _prepared(db, book, tmp_path, config)

    hits = hybrid_search(
        db, PATIENCE, provider=_provider(config),
        model_name=config.model_name, model_version=config.model_version,
    )
    hit = next(h for h in hits if h.chunk_id == chunks[0].chunk_id)
    stored = db.get(ContentChunk, chunks[0].id)
    assert hit.source == source.sha256
    assert hit.source_id == str(source.id)
    assert hit.source_type == "pdf"
    assert hit.language == "en"
    assert hit.content_id == str(stored.id)
    assert hit.book_id == str(book.id)
    assert hit.chapter_id == str(stored.chapter_id)


def test_hybrid_empty_query(db: Session) -> None:
    config = _config()
    assert hybrid_search(
        db, "   ", provider=None, model_name=config.model_name
    ) == []


def test_hybrid_limit_applies(db: Session, tmp_path: Path) -> None:
    config = _config()
    book, _ = _make_book(db, "56" * 32, [PATIENCE, SABR])
    _prepared(db, book, tmp_path, config)

    hits = hybrid_search(
        db, PATIENCE, provider=_provider(config),
        model_name=config.model_name, limit=1,
    )
    assert len(hits) <= 1