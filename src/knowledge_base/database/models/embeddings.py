"""Embeddings domain: models and their vectors.

Vectors are stored with pgvector in a ``vector(n)`` column and HNSW-indexed
for ANN search. Each embedding is tagged with its model version so mixed-model
vectors never silently collide (``UNIQUE(model_id, content_chunk_id)``).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from knowledge_base.database.models.structure import ContentChunk

# Default embedding dimensionality for the base vector column. Production
# models may carry their own dimensions via embedding_models.dimensions; the
# physical column keeps a fixed size so the HNSW index can be created.
_DEFAULT_DIMENSIONS = 768


class EmbeddingModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An embedding model registered with the knowledge base."""

    __tablename__ = "embedding_models"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_embedding_models_name_version"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)

    embeddings: Mapped[list[Embedding]] = relationship(back_populates="model")

    def __repr__(self) -> str:
        return f"<EmbeddingModel {self.name} v{self.version} ({self.dimensions}d)>"


class Embedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One vector for one chunk, produced by one model version."""

    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("model_id", "content_chunk_id", name="uq_embeddings_model_chunk"),
        Index("ix_embeddings_content_chunk_id", "content_chunk_id"),
    )

    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("embedding_models.id"), nullable=False
    )
    content_chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_chunks.id"), nullable=False
    )
    vector: Mapped[list[float]] = mapped_column(Vector(_DEFAULT_DIMENSIONS), nullable=False)

    model: Mapped[EmbeddingModel] = relationship(back_populates="embeddings")
    chunk: Mapped[ContentChunk] = relationship()

    def __repr__(self) -> str:
        return f"<Embedding model={self.model_id} chunk={self.content_chunk_id}>"