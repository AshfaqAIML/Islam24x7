"""Search domain: full-text search documents.

``search_documents`` stores the normalized search variant plus a PostgreSQL
``tsvector`` column (GIN-indexed) so FTS queries run entirely in the database.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, make_enum
from knowledge_base.database.enums import Language

if TYPE_CHECKING:
    from knowledge_base.database.models.structure import ContentChunk


class SearchDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A FTS-optimized view of one chunk, in one language.

    The ``search_vector`` tsvector column is populated by a database trigger on
    insert/update from ``body_text`` using the document's language
    configuration; a GIN index serves full-text queries.
    """

    __tablename__ = "search_documents"
    __table_args__ = (
        UniqueConstraint("content_chunk_id", "language", name="uq_search_docs_chunk_language"),
        Index("ix_search_documents_language", "language"),
        Index("ix_search_documents_vector", "search_vector", postgresql_using="gin"),
    )

    content_chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_chunks.id"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[Language] = mapped_column(make_enum(Language), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str] = mapped_column(TSVECTOR, nullable=True)

    chunk: Mapped[ContentChunk] = relationship(back_populates="search_documents")

    def __repr__(self) -> str:
        return f"<SearchDocument {self.document_type} [{self.language.value}]>"