"""Quran domain: surahs, ayahs, and translations.

Canonical identifiers are the natural keys ``surah number`` and
``surah + ayah number``; these are stable and unique. Text is derived from an
authenticated source file and never "corrected".
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from knowledge_base.database.models.sources import SourceFile


class Surah(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One surah (chapter) of the Quran."""

    __tablename__ = "surahs"
    __table_args__ = (UniqueConstraint("number", name="uq_surahs_number"),)

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name_arabic: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_transliteration: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ayah_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revelation_place: Mapped[str | None] = mapped_column(String(32), nullable=True)

    ayahs: Mapped[list[Ayah]] = relationship(
        back_populates="surah", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Surah {self.number} {self.name_arabic}>"


class Ayah(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One ayah of the Quran."""

    __tablename__ = "ayahs"
    __table_args__ = (
        UniqueConstraint("surah_id", "number", name="uq_ayahs_surah_number"),
        Index("ix_ayahs_surah_id", "surah_id"),
        Index("ix_ayahs_number", "number"),
        Index("ix_ayahs_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_ayahs_search_vector_norm",
            "search_vector_norm",
            postgresql_using="gin",
        ),
    )

    surah_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("surahs.id"), nullable=False
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    juz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    # Diacritic-stripped, letter-normalized Arabic vector (see search/arabic.py).
    # Populated by the seed/backfill layer so Unicode variant letters match
    # queries typed without tashkeel.
    search_vector_norm: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    surah: Mapped[Surah] = relationship(back_populates="ayahs")
    source_file: Mapped[SourceFile] = relationship()
    translations: Mapped[list[Translation]] = relationship(
        back_populates="ayah", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Ayah {self.surah_id}:{self.number}>"


class Translation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A translation of a single ayah into another language."""

    __tablename__ = "ayah_translations"
    __table_args__ = (
        UniqueConstraint("ayah_id", "language", "translator", name="uq_ayah_trans_ayah_lang_tr"),
        Index("ix_ayah_translations_language", "language"),
        Index("ix_ayah_translations_search_vector", "search_vector", postgresql_using="gin"),
    )

    ayah_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ayahs.id"), nullable=False
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    translator: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    ayah: Mapped[Ayah] = relationship(back_populates="translations")
    source_file: Mapped[SourceFile] = relationship()

    def __repr__(self) -> str:
        return f"<Translation {self.language} by {self.translator} of {self.ayah_id}>"