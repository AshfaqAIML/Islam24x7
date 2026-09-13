"""Sources domain: raw files, editions, licenses, and processing jobs.

These tables track the physical, legal, and operational facts about where
content came from. Large binary content (PDFs) is **never** stored here —
only the path and the SHA-256 content hash.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, make_enum
from knowledge_base.database.enums import (
    JobStatus,
    JobType,
    LicenseType,
    SourceFormat,
    SourceStatus,
)

if TYPE_CHECKING:
    from knowledge_base.database.models.books import Book
    from knowledge_base.database.models.metadata import MetadataCandidate
    from knowledge_base.database.models.ocr import OcrPage
    from knowledge_base.database.models.structure import ContentChunk, Page


class SourceFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A raw source file registered into the knowledge base.

    ``sha256`` is the stable, content-addressed identifier used across the
    whole pipeline; renaming/moving a file never changes it.
    """

    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_source_files_sha256"),
        Index("ix_source_files_status", "status"),
    )

    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[SourceFormat] = mapped_column(make_enum(SourceFormat), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        make_enum(SourceStatus), nullable=False, default=SourceStatus.REGISTERED
    )
    title_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)

    editions: Mapped[list[SourceEdition]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    licenses: Mapped[list[License]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    ocr_pages: Mapped[list[OcrPage]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    metadata_candidates: Mapped[list[MetadataCandidate]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    pages: Mapped[list[Page]] = relationship(back_populates="source_file")
    chunks: Mapped[list[ContentChunk]] = relationship(back_populates="source_file")
    books: Mapped[list[Book]] = relationship(back_populates="source_file")

    def __repr__(self) -> str:
        return f"<SourceFile {self.sha256[:8]} {self.format} status={self.status.value}>"


class SourceEdition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A published edition of a work, derived from one source file.

    Books link here; a single raw file typically corresponds to one edition.
    """

    __tablename__ = "source_editions"
    __table_args__ = (
        UniqueConstraint("source_file_id", name="uq_source_editions_source_file"),
        UniqueConstraint("isbn", name="uq_source_editions_isbn"),
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(nullable=True)
    isbn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_file: Mapped[SourceFile] = relationship(back_populates="editions")
    books: Mapped[list[Book]] = relationship(back_populates="edition")

    def __repr__(self) -> str:
        return f"<SourceEdition {self.title!r} ({self.language})>"


class License(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Copyright / distribution license for a source file."""

    __tablename__ = "licenses"
    __table_args__ = (
        UniqueConstraint("source_file_id", "license_type", name="uq_licenses_file_type"),
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    license_type: Mapped[LicenseType] = mapped_column(make_enum(LicenseType), nullable=False)
    holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expiry_at: Mapped[datetime | None] = mapped_column(nullable=True)
    rights: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_file: Mapped[SourceFile] = relationship(back_populates="licenses")

    def __repr__(self) -> str:
        return f"<License {self.license_type.value} for {self.source_file_id}>"


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One run of one pipeline stage against one source file.

    ``UNIQUE(source_file_id, job_type)`` makes stages idempotent: a stage is
    re-run by replacing its latest record, never by duplicating it.
    """

    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("source_file_id", "job_type", name="uq_processing_jobs_file_type"),
        Index("ix_processing_jobs_status", "status"),
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    job_type: Mapped[JobType] = mapped_column(make_enum(JobType), nullable=False)
    status: Mapped[JobStatus] = mapped_column(make_enum(JobStatus), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source_file: Mapped[SourceFile] = relationship(back_populates="jobs")

    def __repr__(self) -> str:
        return f"<ProcessingJob {self.job_type.value} status={self.status.value}>"