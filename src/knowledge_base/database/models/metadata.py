"""Metadata candidates domain: extracted bibliographic data awaiting review.

One row per candidate field/value pair extracted from a source file. A single
source file can yield several candidates for the same field (PDF metadata,
filename, title page, first pages, user input) — each carrying its own
confidence, uncertainty flag, provenance, and human-review state.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, make_enum
from knowledge_base.database.enums import (
    MetadataConfidence,
    MetadataField,
    MetadataReviewStatus,
    MetadataSource,
)

if TYPE_CHECKING:
    from knowledge_base.database.models.sources import SourceFile


class MetadataCandidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One extracted (or user-provided) metadata value for a source file.

    ``field + value + source`` is the natural dedupe key across re-runs;
    re-extraction preserves the review state of existing candidates and only
    reconciles removed/added values. Review decisions are never overwritten by
    a re-run.
    """

    __tablename__ = "metadata_candidates"
    __table_args__ = (
        Index("ix_metadata_candidates_file_field_status", "source_file_id", "field", "status"),
        Index("ix_metadata_candidates_status", "status"),
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    field: Mapped[MetadataField] = mapped_column(make_enum(MetadataField), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[MetadataConfidence] = mapped_column(
        make_enum(MetadataConfidence), nullable=False
    )
    uncertain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[MetadataSource] = mapped_column(make_enum(MetadataSource), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MetadataReviewStatus] = mapped_column(
        make_enum(MetadataReviewStatus), nullable=False, default=MetadataReviewStatus.PENDING
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source_file: Mapped[SourceFile] = relationship(back_populates="metadata_candidates")

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field.value,
            "value": self.value,
            "confidence": self.confidence.value,
            "uncertain": self.uncertain,
            "source": self.source.value,
            "evidence": self.evidence,
            "status": self.status.value,
            "review_note": self.review_note,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
        }

    def __repr__(self) -> str:
        return (
            f"<MetadataCandidate {self.field.value}={self.value!r} "
            f"src={self.source.value} conf={self.confidence.value} "
            f"status={self.status.value}>"
        )


__all__ = ["MetadataCandidate"]