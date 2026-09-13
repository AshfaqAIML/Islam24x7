"""Normalization domain: the search-normalized variant of each content block.

Central invariant: ``content_blocks.original_text`` is the immutable source of
truth and is **never** updated by the normalization pipeline. Each row here is
the separate, search-oriented variant plus an integrity hash of the original
text it was derived from, so a later reader can prove the source never
changed after normalization.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, make_enum
from knowledge_base.database.enums import Language

if TYPE_CHECKING:
    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.sources import SourceFile
    from knowledge_base.database.models.structure import ContentBlock


class NormalizedText(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Search-normalized variant of one content block.

    Deleting the owning ``content_block`` cascades here (DB-level ``ON DELETE
    CASCADE``), so re-running structure detection safely wipes stale
    normalizations too.
    """

    __tablename__ = "normalized_texts"
    __table_args__ = (
        UniqueConstraint("content_block_id", name="uq_normalized_texts_content_block"),
        Index("ix_normalized_texts_book_id", "book_id"),
    )

    content_block_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("content_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[Language] = mapped_column(make_enum(Language), nullable=False)
    config_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    original_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stats: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    content_block: Mapped[ContentBlock] = relationship(back_populates="normalization")
    book: Mapped[Book] = relationship(back_populates="normalizations")
    source_file: Mapped[SourceFile] = relationship()

    def __repr__(self) -> str:
        return (
            f"<NormalizedText block={self.content_block_id} "
            f"[{self.language.value}] protected={self.protected}>"
        )