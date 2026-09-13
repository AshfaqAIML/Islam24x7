"""Book structure domain: the backbones of provenance.

Every content row carries ``source_file_id``, ``page_number`` (where
applicable), ``parent_id``, and ``sequence`` so any chunk can be traced back
to its book, page, and raw source file.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, make_enum
from knowledge_base.database.enums import BlockType, ChapterKind, ContentStatus, Language

if TYPE_CHECKING:
    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.normalization import NormalizedText
    from knowledge_base.database.models.search import SearchDocument
    from knowledge_base.database.models.sources import SourceFile


class Chapter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A top-level container of a book.

    ``kind`` distinguishes real chapters from structural regions the detector
    identifies (front matter, table of contents, appendix) so body text is
    never mistaken for them while provenance is still preserved.
    """

    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("book_id", "number", name="uq_chapters_book_number"),
        Index("ix_chapters_book_id", "book_id"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[ChapterKind] = mapped_column(
        make_enum(ChapterKind), nullable=False, default=ChapterKind.CHAPTER
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )

    book: Mapped[Book] = relationship(back_populates="chapters")
    source_file: Mapped[SourceFile] = relationship()
    sections: Mapped[list[Section]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Chapter {self.number} {self.title!r}>"


class Section(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A section nested under a chapter."""

    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("chapter_id", "number", name="uq_sections_chapter_number"),
        Index("ix_sections_chapter_id", "chapter_id"),
    )

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chapters.id"), nullable=False
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )

    book: Mapped[Book] = relationship(back_populates="sections")
    chapter: Mapped[Chapter] = relationship(back_populates="sections")
    source_file: Mapped[SourceFile] = relationship()
    subsections: Mapped[list[Subsection]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Section {self.number} {self.title!r}>"


class Subsection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A subsection nested under a section."""

    __tablename__ = "subsections"
    __table_args__ = (
        UniqueConstraint("section_id", "number", name="uq_subsections_section_number"),
        Index("ix_subsections_book_id", "book_id"),
        Index("ix_subsections_section_id", "section_id"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )

    book: Mapped[Book] = relationship(back_populates="subsections")
    section: Mapped[Section] = relationship(back_populates="subsections")
    source_file: Mapped[SourceFile] = relationship()

    def __repr__(self) -> str:
        return f"<Subsection {self.number} {self.title!r}>"


class Page(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical page of a book (1-based page number from the source)."""

    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("book_id", "page_number", name="uq_pages_book_number"),
        Index("ix_pages_source_file_id", "source_file_id"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    has_text: Mapped[bool] = mapped_column(nullable=False, default=False)

    book: Mapped[Book] = relationship(back_populates="pages")
    source_file: Mapped[SourceFile] = relationship(back_populates="pages")
    paragraphs: Mapped[list[Paragraph]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )
    content_blocks: Mapped[list[ContentBlock]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Page {self.page_number} of {self.book_id}>"


class Paragraph(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A paragraph of original (pre-normalization) text on a page."""

    __tablename__ = "paragraphs"
    __table_args__ = (
        UniqueConstraint("book_id", "page_id", "sequence", name="uq_paragraphs_book_page_seq"),
        Index("ix_paragraphs_page_id", "page_id"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pages.id"), nullable=False
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    book: Mapped[Book] = relationship(back_populates="paragraphs")
    page: Mapped[Page] = relationship(back_populates="paragraphs")
    source_file: Mapped[SourceFile] = relationship()


class ContentBlock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A typed content element (paragraph, verse, hadith, footnote, ...)."""

    __tablename__ = "content_blocks"
    __table_args__ = (
        UniqueConstraint("book_id", "page_id", "sequence", name="uq_blocks_book_page_seq"),
        Index("ix_blocks_page_id", "page_id"),
        Index("ix_blocks_chapter_id", "chapter_id"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pages.id"), nullable=True
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chapters.id"), nullable=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id"), nullable=True
    )
    subsection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subsections.id"), nullable=True
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    block_type: Mapped[BlockType] = mapped_column(make_enum(BlockType), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        make_enum(ContentStatus), nullable=False, default=ContentStatus.PENDING
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    book: Mapped[Book] = relationship(back_populates="content_blocks")
    page: Mapped[Page | None] = relationship(back_populates="content_blocks")
    chapter: Mapped[Chapter | None] = relationship()
    section: Mapped[Section | None] = relationship()
    subsection: Mapped[Subsection | None] = relationship()
    source_file: Mapped[SourceFile] = relationship()
    chunks: Mapped[list[ContentChunk]] = relationship(
        back_populates="content_block", cascade="all, delete-orphan"
    )
    normalization: Mapped[NormalizedText | None] = relationship(
        back_populates="content_block", cascade="all, delete-orphan"
    )

    @property
    def page_number(self) -> int | None:
        return self.page.page_number if self.page else None


class ContentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A structure-aware retrieval chunk with a stable, deterministic id.

    Chunks group consecutive paragraphs within one section (never splitting a
    paragraph and never crossing a section/chapter boundary). ``chunk_id`` is
    derived from source hash + last structure position so re-running the
    pipeline produces identical ids (no churn across incremental runs).
    ``content_block_id`` is the *first* block in the chunk; every block id is
    repeated in ``metadata_['block_ids']``.
    """

    __tablename__ = "content_chunks"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_content_chunks_chunk_id"),
        Index("ix_content_chunks_book_id", "book_id"),
    )

    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    book_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    content_block_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("content_blocks.id"), nullable=False
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chapters.id"), nullable=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id"), nullable=True
    )
    language: Mapped[Language] = mapped_column(make_enum(Language), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_normalized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    status: Mapped[ContentStatus] = mapped_column(
        make_enum(ContentStatus), nullable=False, default=ContentStatus.PENDING
    )

    book: Mapped[Book] = relationship(back_populates="content_chunks")
    content_block: Mapped[ContentBlock] = relationship(back_populates="chunks")
    source_file: Mapped[SourceFile] = relationship(back_populates="chunks")
    search_documents: Mapped[list[SearchDocument]] = relationship(back_populates="chunk")

    def __repr__(self) -> str:
        return f"<ContentChunk {self.chunk_id}>"