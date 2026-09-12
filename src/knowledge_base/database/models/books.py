"""Books catalog domain.

Works-level metadata (the intellectual entities) is kept separate from the
physical source files. The chain ``Book -> SourceFile -> SourceEdition`` links
the catalog to its provenance.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Index, String, Table, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from knowledge_base.database.models.sources import SourceEdition, SourceFile
    from knowledge_base.database.models.structure import (
        Chapter,
        ContentBlock,
        ContentChunk,
        Page,
        Paragraph,
        Section,
    )


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Top-level classification of a book (fiqh, tafsir, aqeedah, ...)."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("code", name="uq_categories_code"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    topics: Mapped[list[Topic]] = relationship(back_populates="category")
    books: Mapped[list[Book]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.code!r}>"


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A topic a book can be tagged with (many-to-many with books)."""

    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("name", name="uq_topics_name"),
        UniqueConstraint("category_id", "name", name="uq_topics_category_name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )

    category: Mapped[Category | None] = relationship(back_populates="topics")
    books: Mapped[list[Book]] = relationship(
        secondary="book_topics", back_populates="topics"
    )

    def __repr__(self) -> str:
        return f"<Topic {self.name!r}>"


book_topics = Table(
    "book_topics",
    Base.metadata,
    Column("book_id", Uuid(as_uuid=True), ForeignKey("books.id"), primary_key=True),
    Column("topic_id", Uuid(as_uuid=True), ForeignKey("topics.id"), primary_key=True),
)


class Author(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Author of a book."""

    __tablename__ = "authors"
    __table_args__ = (UniqueConstraint("name", name="uq_authors_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_arabic: Mapped[str | None] = mapped_column(String(255), nullable=True)

    books: Mapped[list[Book]] = relationship(back_populates="author")

    def __repr__(self) -> str:
        return f"<Author {self.name!r}>"


class Translator(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Translator of a book (or a hadith/ayah translation)."""

    __tablename__ = "translators"
    __table_args__ = (UniqueConstraint("name", name="uq_translators_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<Translator {self.name!r}>"


class Publisher(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Publisher of a book edition."""

    __tablename__ = "publishers"
    __table_args__ = (UniqueConstraint("name", name="uq_publishers_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Publisher {self.name!r}>"


class Book(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A book in the knowledge base, bound to its source file and edition.

    Provenance: ``Book -> SourceFile -> SourceEdition -> (chapters, pages, ...)``.
    """

    __tablename__ = "books"
    __table_args__ = (
        UniqueConstraint("source_file_id", "title", name="uq_books_source_title"),
        Index("ix_books_category_id", "category_id"),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_editions.id"), nullable=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("authors.id"), nullable=True
    )
    translator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("translators.id"), nullable=True
    )
    publisher_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("publishers.id"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )

    source_file: Mapped[SourceFile] = relationship(back_populates="books")
    edition: Mapped[SourceEdition | None] = relationship(back_populates="books")
    author: Mapped[Author | None] = relationship(back_populates="books")
    translator: Mapped[Translator | None] = relationship()
    publisher: Mapped[Publisher | None] = relationship()
    category: Mapped[Category | None] = relationship(back_populates="books")
    topics: Mapped[list[Topic]] = relationship(
        secondary="book_topics", back_populates="books"
    )

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    sections: Mapped[list[Section]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    pages: Mapped[list[Page]] = relationship(back_populates="book", cascade="all, delete-orphan")
    paragraphs: Mapped[list[Paragraph]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    content_blocks: Mapped[list[ContentBlock]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    content_chunks: Mapped[list[ContentChunk]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Book {self.title!r}>"