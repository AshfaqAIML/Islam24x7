"""Hadith domain: collections, hadith books, chapters, and hadiths.

Natural keys follow the classical referencing scheme (collection + hadith
number, e.g. ``bukhari 1``), which is stable across editions.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from knowledge_base.database.models.sources import SourceFile


class Collection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A hadith collection (Sahih al-Bukhari, Sahih Muslim, ...)."""

    __tablename__ = "hadith_collections"
    __table_args__ = (UniqueConstraint("name", name="uq_hadith_collections_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    books: Mapped[list[HadithBook]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    chapters: Mapped[list[HadithChapter]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    hadiths: Mapped[list[Hadith]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Collection {self.name!r}>"


class HadithBook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A book (kitab) inside a hadith collection."""

    __tablename__ = "hadith_books"
    __table_args__ = (
        UniqueConstraint("collection_id", "name", name="uq_hadith_books_collection_name"),
        Index("ix_hadith_books_collection_id", "collection_id"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hadith_collections.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    collection: Mapped[Collection] = relationship(back_populates="books")
    chapters: Mapped[list[HadithChapter]] = relationship(
        back_populates="hadith_book", cascade="all, delete-orphan"
    )
    hadiths: Mapped[list[Hadith]] = relationship(back_populates="hadith_book")

    def __repr__(self) -> str:
        return f"<HadithBook {self.name!r} in {self.collection_id}>"


class HadithChapter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A chapter (baab) inside a collection (optionally within a hadith book)."""

    __tablename__ = "hadith_chapters"
    __table_args__ = (
        UniqueConstraint("collection_id", "name", name="uq_hadith_chapters_collection_name"),
        Index("ix_hadith_chapters_collection_id", "collection_id"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hadith_collections.id"), nullable=False
    )
    hadith_book_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hadith_books.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    collection: Mapped[Collection] = relationship(back_populates="chapters")
    hadith_book: Mapped[HadithBook | None] = relationship(back_populates="chapters")
    hadiths: Mapped[list[Hadith]] = relationship(back_populates="hadith_chapter")

    def __repr__(self) -> str:
        return f"<HadithChapter {self.name!r}>"


class Hadith(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single hadith with its classical identifiers and provenance."""

    __tablename__ = "hadiths"
    __table_args__ = (
        UniqueConstraint("collection_id", "number", name="uq_hadiths_collection_number"),
        Index("ix_hadiths_collection_id", "collection_id"),
        Index("ix_hadiths_hadith_chapter_id", "hadith_chapter_id"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hadith_collections.id"), nullable=False
    )
    hadith_book_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hadith_books.id"), nullable=True
    )
    hadith_chapter_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hadith_chapters.id"), nullable=True
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_arabic: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(255), nullable=True)
    narrator: Mapped[str | None] = mapped_column(String(255), nullable=True)

    collection: Mapped[Collection] = relationship(back_populates="hadiths")
    hadith_book: Mapped[HadithBook | None] = relationship(back_populates="hadiths")
    hadith_chapter: Mapped[HadithChapter | None] = relationship(back_populates="hadiths")
    source_file: Mapped[SourceFile] = relationship()

    def __repr__(self) -> str:
        return f"<Hadith {self.collection_id}:{self.number}>"