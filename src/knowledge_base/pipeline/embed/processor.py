"""Embed pipeline stage: generate chunk embeddings into pgvector.

Reads a published book's retrieval chunks, asks the configured (replaceable)
provider for one vector per chunk, and stores the results in ``embeddings``
tagged with the embedding model plus the SHA-256 of the exact chunk text that
produced them.

Incremental and idempotent:

- chunks whose content hash is unchanged keep their existing vector — they are
  **never re-embedded**;
- chunks whose text changed (re-chunked source, provider upgrade by
  ``model_version``) are re-embedded in place;
- the book's single ``EMBED`` ``ProcessingJob`` record is replaced on every
  run; a per-book run is all-or-nothing (no partial vectors on failure).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import JobStatus, JobType
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.embeddings import Embedding, EmbeddingModel
from knowledge_base.database.models.structure import ContentChunk
from knowledge_base.logging import logger
from knowledge_base.pipeline.embed.config import EMBEDDING_DIMENSIONS, EmbedConfig
from knowledge_base.pipeline.embed.provider import (
    EmbeddingError,
    EmbeddingProvider,
    RateLimiter,
    embed_with_retry,
)
from knowledge_base.pipeline.jobs import upsert_processing_job


@dataclass
class EmbedResult:
    """Outcome of embedding one book's chunks for one model."""

    sha256: str
    book_id: str
    source_file_id: str
    error: str | None = None
    report_path: Path | None = None
    model_name: str = ""
    model_version: str = ""
    dimensions: int = 0
    chunk_count: int = 0
    embedded_count: int = 0
    updated_count: int = 0
    reused_count: int = 0
    batch_count: int = 0


def embed_book(
    book: Book,
    *,
    session: Session,
    data_dir: Path,
    provider: EmbeddingProvider,
    config: EmbedConfig,
) -> EmbedResult:
    """Generate embeddings for a published book's chunks (incremental)."""
    source_file = book.source_file
    sha256 = source_file.sha256
    book_id = str(book.id)
    result = EmbedResult(
        sha256=sha256,
        book_id=book_id,
        source_file_id=str(source_file.id),
        model_name=config.model_name,
        model_version=config.model_version,
        dimensions=config.dimensions,
    )

    dimension_error = _dimension_error(provider, config)
    if dimension_error is not None:
        result.error = dimension_error
        result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
        _write_report(result)
        _upsert_job(session, result)
        return result

    chunks = _load_chunks(session, book_id)
    if not chunks:
        result.error = "book has no chunks; did the chunk stage run?"
        result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
        _write_report(result)
        _upsert_job(session, result)
        return result

    model = _upsert_model(session, provider=provider, config=config)
    existing = {
        str(row.content_chunk_id): row
        for row in session.scalars(
            select(Embedding).where(
                Embedding.model_id == model.id,
                Embedding.content_chunk_id.in_([c.id for c in chunks]),
            )
        ).all()
    }
    result.chunk_count = len(chunks)

    to_embed: list[tuple[ContentChunk, Embedding | None, str]] = []
    for chunk in chunks:
        content_hash = _content_hash(chunk.text)
        row = existing.get(str(chunk.id))
        if row is not None and row.content_hash == content_hash:
            result.reused_count += 1
            continue
        to_embed.append((chunk, row, content_hash))

    pending: list[tuple[ContentChunk, Embedding | None, str, list[float]]] = []
    limiter = RateLimiter(calls_per_minute=config.calls_per_minute)
    for start in range(0, len(to_embed), config.batch_size):
        batch = to_embed[start : start + config.batch_size]
        texts = [chunk.text for chunk, _row, _hash in batch]
        try:
            limiter.wait()
            vectors = embed_with_retry(
                provider,
                texts,
                max_retries=config.max_retries,
                backoff_seconds=config.backoff_seconds,
            )
        except EmbeddingError as exc:
            result.error = str(exc)
            break
        if len(vectors) != len(batch):
            result.error = (
                f"provider {provider.name} returned {len(vectors)} vectors "
                f"for {len(batch)} texts"
            )
            break
        for (chunk, row, content_hash), vector in zip(batch, vectors, strict=True):
            if len(vector) != config.dimensions:
                result.error = (
                    f"provider {provider.name} returned a {len(vector)}-dimensional "
                    f"vector (expected {config.dimensions})"
                )
                break
            pending.append((chunk, row, content_hash, vector))
        if result.error:
            break
        result.batch_count += 1

    if result.error is not None:
        result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
        _write_report(result)
        _upsert_job(session, result)
        return result

    for chunk, row, content_hash, vector in pending:
        if row is None:
            session.add(
                Embedding(
                    model_id=model.id,
                    content_chunk_id=chunk.id,
                    vector=vector,
                    content_hash=content_hash,
                )
            )
            result.embedded_count += 1
        else:
            row.vector = vector
            row.content_hash = content_hash
            result.updated_count += 1
    session.flush()

    result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
    _write_report(result)
    _upsert_job(session, result)
    return result


def embed_all(
    session: Session,
    *,
    settings: Settings | None = None,
    provider: EmbeddingProvider,
    config: EmbedConfig,
    limit: int | None = None,
) -> list[EmbedResult]:
    """Embed every published book (incremental, idempotent)."""
    if settings is None:
        settings = get_settings()
    books = session.scalars(select(Book).order_by(Book.created_at)).all()
    if limit is not None:
        books = books[:limit]
    results: list[EmbedResult] = []
    for book in books:
        logger.info("embed book={} {}", book.title, book.id)
        results.append(
            embed_book(
                book, session=session, data_dir=settings.data_dir,
                provider=provider, config=config,
            )
        )
    return results


def _load_chunks(session: Session, book_id: str) -> list[ContentChunk]:
    return list(
        session.scalars(
            select(ContentChunk)
            .where(ContentChunk.book_id == book_id)
            .order_by(ContentChunk.sequence)
        )
    )


def _dimension_error(provider: EmbeddingProvider, config: EmbedConfig) -> str | None:
    if provider.dimensions != config.dimensions:
        return (
            f"provider {provider.name} emits {provider.dimensions}-dimensional "
            f"vectors but the pipeline is configured for {config.dimensions} dimensions"
        )
    if config.dimensions != EMBEDDING_DIMENSIONS:
        return (
            f"the embeddings.vector column is {EMBEDDING_DIMENSIONS}-dimensional "
            f"(HNSW index); using {config.dimensions} dimensions needs a migration"
        )
    return None


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _upsert_model(
    session: Session, *, provider: EmbeddingProvider, config: EmbedConfig
) -> EmbeddingModel:
    model = session.scalar(
        select(EmbeddingModel).where(
            EmbeddingModel.name == config.model_name,
            EmbeddingModel.version == config.model_version,
        )
    )
    if model is None:
        model = EmbeddingModel(
            name=config.model_name,
            provider=provider.name,
            dimensions=provider.dimensions,
            version=config.model_version,
        )
        session.add(model)
        session.flush()
    else:
        # Same (name, version) identity — refresh provider facts so the tag
        # always reflects what actually produced the vectors.
        model.provider = provider.name
        model.dimensions = provider.dimensions
    return model


def _report_dir(data_dir: Path) -> Path:
    return data_dir.resolve() / "processed" / "embed"


def _render_report(result: EmbedResult) -> str:
    return (
        f"Embeddings for {result.sha256[:12]} (book {result.book_id[:8]})\n"
        f"Model: {result.model_name} v{result.model_version} "
        f"(dims={result.dimensions})\n"
        f"Chunks={result.chunk_count} embedded={result.embedded_count} "
        f"updated={result.updated_count} reused={result.reused_count} "
        f"batches={result.batch_count}\n"
        + (f"Error: {result.error}\n" if result.error else "")
    )


def _write_report(result: EmbedResult) -> None:
    assert result.report_path is not None
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    result.report_path.write_text(_render_report(result), encoding="utf-8")


def _upsert_job(session: Session, result: EmbedResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.EMBED,
        status=status,
        manifest={
            "model_name": result.model_name,
            "model_version": result.model_version,
            "dimensions": result.dimensions,
            "chunk_count": result.chunk_count,
            "embedded_count": result.embedded_count,
            "updated_count": result.updated_count,
            "reused_count": result.reused_count,
            "batch_count": result.batch_count,
            "report": result.report_path.name if result.report_path else None,
        },
        error=result.error,
    )


__all__ = ["EmbedResult", "embed_all", "embed_book"]