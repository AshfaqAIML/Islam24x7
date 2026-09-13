"""OCR results: one row per page processed by the OCR stage.

OCR output is stored **separately from the source images and the original
PDF** — the normalized page image lives under ``render/`` and the engine
text under ``text/``, while this table records provenance (engine, version,
languages), the outcome, and any quality flags so the review queue is a
simple query.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge_base.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, make_enum
from knowledge_base.database.enums import OcrStatus

if TYPE_CHECKING:
    from knowledge_base.database.models.sources import SourceFile


class OcrPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The OCR outcome for a single, original PDF page number."""

    __tablename__ = "ocr_pages"
    __table_args__ = (
        UniqueConstraint("source_file_id", "page_number", name="uq_ocr_pages_file_page"),
        Index("ix_ocr_pages_status", "status"),
        Index("ix_ocr_pages_source_file_id", "source_file_id"),
    )

    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_files.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    languages: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[OcrStatus] = mapped_column(
        make_enum(OcrStatus), nullable=False, default=OcrStatus.OK
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_file: Mapped[SourceFile] = relationship(back_populates="ocr_pages")

    def __repr__(self) -> str:
        return (
            f"<OcrPage page={self.page_number} status={self.status.value}"
            f" conf={self.confidence}>"
        )