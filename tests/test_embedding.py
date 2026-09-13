"""Tests for the embeddings milestone.

Covers the ``EMBED`` pipeline stage: provider-driven vector generation,
version tracking, content-hash incremental processing (unchanged chunks are
never re-embedded), idempotency, failure handling (retries, rate limits,
failed jobs) and the deterministic dummy provider's similarity semantics.
"""

from __future__ import annotations

import hashlib
from math import sqrt
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from knowledge_base.database.enums import (
    BlockType,
    JobStatus,
    JobType,
    SourceFormat,
)
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.embeddings import Embedding, EmbeddingModel
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
from knowledge_base.pipeline.embed.config import EmbedConfig
from knowledge_base.pipeline.embed.processor import embed_book
from knowledge_base.pipeline.embed.provider import (
    DummyEmbeddingProvider,
    EmbeddingError,
    EmbeddingProviderUnavailable,
    RateLimitedError,
    RateLimiter,
    build_provider,
    embed_with_retry,
)

DIMS = 768


def _config(**overrides) -> EmbedConfig:
    defaults = dict(
        model_name="kb-test",
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
    session: Session, sha256: str, texts: list[str], *, language: str | None = "en"
) -> tuple[Book, SourceFile]:
    source = SourceFile(
        sha256=sha256, file_path=f"books/{sha256}.pdf", format=SourceFormat.PDF
    )
    session.add(source)
    session.flush()
    book = Book(source_file_id=source.id, title="Embedding Fixture", language=language)
    session.add(book)
    session.flush()
    chapter = Chapter(
        book_id=book.id, number=1, title="Chapter 1", source_file_id=source.id
    )
    session.add(chapter)
    session.flush()
    section = Section(
        book_id=book.id, chapter_id=chapter.id, number=1, title="Section 1",
        source_file_id=source.id,
    )
    session.add(section)
    session.flush()
    page = Page(
        book_id=book.id, source_file_id=source.id, page_number=1, has_text=True
    )
    session.add(page)
    session.flush()
    for idx, text in enumerate(texts, start=1):
        session.add(
            ContentBlock(
                book_id=book.id,
                page_id=page.id,
                chapter_id=chapter.id,
                section_id=section.id,
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
    return session.scalars(
        select(ContentChunk)
        .where(ContentChunk.book_id == book.id)
        .order_by(ContentChunk.sequence)
    ).all()


def _embeddings(session: Session, model: EmbeddingModel) -> list[Embedding]:
    return session.scalars(
        select(Embedding)
        .where(Embedding.model_id == model.id)
        .order_by(Embedding.created_at)
    ).all()


def _model(session: Session, **where) -> EmbeddingModel | None:
    return session.scalar(select(EmbeddingModel).filter_by(**where))


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


TEXTS = [
    "The prayer and the fasting are acts of worship.",
    "The sunnah of the Prophet guides our daily habits.",
]


# ------------------------------------------------------------- embed stage

def test_embed_book_populates_embeddings(db: Session, tmp_path: Path) -> None:
    book, source = _make_book(db, "11" * 32, TEXTS)
    chunks = _chunked(db, book, tmp_path)
    config = _config()

    result = embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()
    db.expire_all()

    assert result.error is None
    assert result.chunk_count == len(chunks)
    assert result.embedded_count == len(chunks)
    assert result.reused_count == 0

    model = _model(db, name="kb-test", version="0.1.0")
    assert model is not None
    assert model.provider == "dummy"
    assert model.dimensions == DIMS

    rows = _embeddings(db, model)
    assert len(rows) == len(chunks)
    for row in rows:
        assert len(list(row.vector)) == DIMS
        assert row.content_hash == _content_hash(
            db.scalar(select(ContentChunk.text).where(ContentChunk.id == row.content_chunk_id))
        )

    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.EMBED,
        )
    ).one()
    assert job.status == JobStatus.SUCCEEDED
    assert job.manifest["model_name"] == "kb-test"
    assert job.manifest["embedded_count"] == len(chunks)
    assert job.manifest["reused_count"] == 0

    report = tmp_path / "processed" / "embed" / f"{'11' * 32}.txt"
    assert report.is_file()


def test_embed_book_reuses_unchanged_chunks(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "22" * 32, TEXTS)
    chunks = _chunked(db, book, tmp_path)
    config = _config()
    first = embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()
    db.expire_all()
    assert first.embedded_count == len(chunks)

    vectors_before = {}
    model = _model(db, name="kb-test")
    assert model is not None
    for row in _embeddings(db, model):
        vectors_before[str(row.content_chunk_id)] = list(row.vector)

    second = embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()
    db.expire_all()

    assert second.error is None
    assert second.embedded_count == 0
    assert second.updated_count == 0
    assert second.reused_count == len(chunks)

    model = _model(db, name="kb-test")
    assert model is not None
    count = db.scalar(
        select(func.count()).select_from(Embedding).where(
            Embedding.model_id == model.id
        )
    )
    assert count == len(chunks)

    for chunk in chunks:
        row = db.scalar(
            select(Embedding).where(
                Embedding.model_id == model.id,
                Embedding.content_chunk_id == chunk.id,
            )
        )
        assert list(row.vector) == vectors_before[str(chunk.id)]


def test_embed_book_regenerates_only_changed_chunk(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "23" * 32, TEXTS)
    chunks = _chunked(db, book, tmp_path)
    config = _config()
    embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()

    target = chunks[0]
    new_text = target.text + " and the remembrance of God."
    db.execute(update(ContentChunk).where(ContentChunk.id == target.id).values(text=new_text))
    db.flush()
    db.expire_all()

    result = embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()
    db.expire_all()

    assert result.error is None
    assert result.embedded_count == 0
    assert result.updated_count == 1
    assert result.reused_count == len(chunks) - 1

    model = _model(db, name="kb-test")
    assert model is not None
    row = db.scalar(
        select(Embedding).where(
            Embedding.model_id == model.id, Embedding.content_chunk_id == target.id
        )
    )
    assert row.content_hash == _content_hash(new_text)


def test_embed_book_new_version_embeds_all_fresh(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "24" * 32, TEXTS)
    chunks = _chunked(db, book, tmp_path)
    embed_book(
        book, session=db, data_dir=tmp_path,
        provider=_provider(_config()), config=_config(),
    )
    db.flush()

    config_v2 = _config(model_version="0.2.0")
    result = embed_book(
        book, session=db, data_dir=tmp_path,
        provider=_provider(config_v2), config=config_v2,
    )
    db.flush()
    db.expire_all()

    assert result.embedded_count == len(chunks)
    assert result.reused_count == 0

    old = _model(db, name="kb-test", version="0.1.0")
    new = _model(db, name="kb-test", version="0.2.0")
    assert old is not None and new is not None
    assert len(_embeddings(db, old)) == len(chunks)  # old vectors preserved
    assert len(_embeddings(db, new)) == len(chunks)


def test_embed_book_no_chunks_failed_job(db: Session, tmp_path: Path) -> None:
    book, source = _make_book(db, "25" * 32, [])
    config = _config()
    result = embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()

    assert result.error is not None
    assert "no chunks" in result.error
    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.EMBED,
        )
    ).one()
    assert job.status == JobStatus.FAILED
    assert job.error == result.error


def test_embed_book_provider_failure_marks_failed_without_partial_rows(
    db: Session, tmp_path: Path
) -> None:
    book, source = _make_book(db, "26" * 32, TEXTS)
    _chunked(db, book, tmp_path)

    class FailingProvider:
        name = "flaky"
        version = "0.1.0"
        dimensions = DIMS

        def embed(self, texts):
            raise EmbeddingError("provider boom")

    config = _config(max_retries=1)
    result = embed_book(
        book, session=db, data_dir=tmp_path, provider=FailingProvider(), config=config
    )
    db.flush()

    assert result.error is not None
    assert "after 2 attempts" in result.error
    job = db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.EMBED,
        )
    ).one()
    assert job.status == JobStatus.FAILED

    model = _model(db, name="kb-test")
    count = db.scalar(
        select(func.count()).select_from(Embedding).where(
            Embedding.model_id == model.id
        )
    )
    assert count == 0  # all-or-nothing: no partial vectors


def test_embed_book_wrong_dimensions_fails(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "27" * 32, TEXTS)
    _chunked(db, book, tmp_path)
    config = _config(dimensions=DIMS)
    wrong = DummyEmbeddingProvider(dimensions=512)
    result = embed_book(book, session=db, data_dir=tmp_path, provider=wrong, config=config)
    db.flush()
    assert result.error is not None
    assert "512-dimensional" in result.error


# ------------------------------------------- provider behaviour (unit level)

def test_dummy_provider_deterministic_unit_norm_and_similarity() -> None:
    provider = DummyEmbeddingProvider(dimensions=DIMS)
    a = provider.embed(["the prayer of the fasting believer"])[0]
    b = provider.embed(["the prayer of the fasting believer"])[0]
    assert a == b
    norm = sqrt(sum(v * v for v in a))
    assert abs(norm - 1.0) < 1e-9

    similar = provider.embed(["the prayer and the fasting are worship"])[0]
    unrelated = provider.embed(["rock climbing equipment and steel carabiners"])[0]

    def cosine(x, y: list[float]) -> float:
        return sum(i * j for i, j in zip(x, y, strict=True)) / (
            sqrt(sum(i * i for i in x)) * sqrt(sum(j * j for j in y))
        )

    assert cosine(a, similar) > cosine(a, unrelated)


def test_identical_chunks_store_identical_vectors(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(
        db,
        "28" * 32,
        ["exactly the same text exactly the same text exactly the same text"] * 2,
    )
    _chunked(db, book, tmp_path)
    config = _config()
    embed_book(
        book, session=db, data_dir=tmp_path, provider=_provider(config), config=config
    )
    db.flush()
    model = _model(db, name="kb-test")
    assert model is not None
    rows = _embeddings(db, model)
    assert len(rows) == 2
    assert list(rows[0].vector) == list(rows[1].vector)


def test_embed_with_retry_recovers_from_rate_limit() -> None:
    class FlakyProvider:
        name = "flaky"
        version = "0.1.0"
        dimensions = DIMS

        def __init__(self) -> None:
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitedError("slow down")
            return [[1.0] + [0.0] * (DIMS - 1) for _ in texts]

    provider = FlakyProvider()
    vectors = embed_with_retry(
        provider, ["one", "two"], max_retries=3, backoff_seconds=0.0
    )
    assert len(vectors) == 2
    assert len(vectors[0]) == DIMS
    assert provider.calls == 2


def test_embed_with_retry_exhausts_and_raises() -> None:
    class AlwaysDown:
        name = "down"
        version = "0.1.0"
        dimensions = DIMS

        def embed(self, texts):
            raise EmbeddingError("timeout")

    with pytest.raises(EmbeddingError, match="after 2 attempts"):
        embed_with_retry(AlwaysDown(), ["x"], max_retries=1, backoff_seconds=0.0)


def test_rate_limiter_no_limit_passes() -> None:
    limiter = RateLimiter()
    limiter.wait()  # must not block
    limiter.wait()
    assert limiter.min_interval == 0.0


def test_build_provider_unknown_and_custom_path() -> None:
    config = _config()
    with pytest.raises(EmbeddingProviderUnavailable):
        build_provider("no-such-provider", config)

    custom = build_provider(
        "knowledge_base.pipeline.embed.provider:DummyEmbeddingProvider", config
    )
    assert isinstance(custom, DummyEmbeddingProvider)
    assert custom.dimensions == DIMS


def test_embed_model_uniqueness_by_name_version(db: Session, tmp_path: Path) -> None:
    book, _ = _make_book(db, "29" * 32, TEXTS)
    _chunked(db, book, tmp_path)
    config = _config()
    for _ in range(2):
        embed_book(
            book, session=db, data_dir=tmp_path,
            provider=_provider(config), config=config,
        )
        db.flush()
    db.expire_all()
    models = db.scalars(select(EmbeddingModel)).all()
    assert len(models) == 1
    assert (models[0].name, models[0].version) == ("kb-test", "0.1.0")