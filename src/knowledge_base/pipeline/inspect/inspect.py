"""PDF inspection: classify a source file for downstream processing.

Analyzes a registered PDF **in place, read-only** (never rendering or
modifying it) and determines:

- file size
- page count
- per-page text selectability and text density
- whether each page appears scanned (images with no reusable text)
- language/script hint (Arabic / Urdu / Latin) where feasible
- PDF metadata and encryption status
- corruption indicators

Each PDF is then classified as one of:

- ``TEXT_PDF``    — selectable text on almost every page
- ``SCANNED_PDF`` — image-only; needs OCR
- ``MIXED_PDF``   — meaningful mix of text and scanned/blank pages
- ``INVALID_PDF`` — cannot be read (missing, corrupt, encrypted, empty)

Outputs:

- ``data/processed/inspect/<sha256>.json`` — full machine-readable report
- ``data/processed/inspect/<sha256>.txt``  — human-readable summary
- a ``ProcessingJob`` of type ``inspect`` whose manifest (including the
  classification) is available to every later pipeline stage
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import JobStatus, JobType, PdfClassification
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.logging import logger
from knowledge_base.pipeline.jobs import upsert_processing_job

_ARABIC_RANGES = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)
_URDU_EXTRA = {0x06BE, 0x06BA, 0x06D2, 0x06CC, 0x0679, 0x0688, 0x06AF, 0x06C1}

# A page with fewer characters than this is treated as having no usable
# text layer (scanned or blank), no matter how many glyphs it "has".
TEXT_MIN_CHARS = 30
# Approximate density bands per page (raw char counts).
DENSITY_LOW = 200
DENSITY_MED = 1200

# Classification thresholds.
TEXT_RATIO = 0.95  # page fraction carrying text -> TEXT_PDF needs ~all pages
SCANNED_TOLERANCE = 0.02  # a scanned page or two keeps a book TEXT_PDF
SCANNED_RATIO = 0.80  # page fraction that is scanned -> SCANNED_PDF
WARNING_SCANNED_RATIO = 0.05  # scanned ratio above this => OCR recommended


def _is_arabic_script(char: str) -> bool:
    code = ord(char)
    return any(start <= code <= end for start, end in _ARABIC_RANGES)


def detect_script_hint(text: str) -> str | None:
    """Return ``ur``, ``ar``, or ``en`` based on the visible script mix.

    Pure function so downstream metadata/validation can reuse it.
    """
    arabic_chars = sum(1 for ch in text if _is_arabic_script(ch))
    latin_chars = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if arabic_chars == 0 and latin_chars == 0:
        return None
    if arabic_chars == 0:
        return "en"
    urdu_chars = sum(1 for ch in text if ord(ch) in _URDU_EXTRA)
    if urdu_chars >= max(3, arabic_chars // 20):
        return "ur"
    return "ar"


def density_band(chars: int) -> str:
    """Approximate per-page text density as a band label."""
    if chars == 0:
        return "none"
    if chars <= DENSITY_LOW:
        return "low"
    if chars <= DENSITY_MED:
        return "medium"
    return "high"


@dataclass
class PageInspection:
    """Per-page facts collected during inspection."""

    page_number: int
    chars: int = 0
    text_selectable: bool = False
    density: str = "none"
    has_images: bool = False
    scanned: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "page": self.page_number,
            "chars": self.chars,
            "text_selectable": self.text_selectable,
            "density": self.density,
            "has_images": self.has_images,
            "scanned": self.scanned,
            "error": self.error,
        }


@dataclass
class InspectionResult:
    """Summary of one inspected PDF."""

    sha256: str
    source_file_id: str
    page_count: int = 0
    file_size: int | None = None
    pages: list[PageInspection] = field(default_factory=list)
    text_pages: int = 0
    scanned_pages: int = 0
    blank_pages: int = 0
    unreadable_pages: int = 0
    chars_total: int = 0
    encrypted: bool = False
    is_repaired: bool = False
    ocr_likely: bool = False
    classification: PdfClassification = PdfClassification.INVALID_PDF
    corruption_flags: list[str] = field(default_factory=list)
    language_hint: str | None = None
    pdf_meta: dict[str, str] = field(default_factory=dict)
    pdf_version: str | None = None
    report_path: Path | None = None
    summary_path: Path | None = None
    error: str | None = None


def _sample_text(document: pymupdf.Document, limit: int = 30) -> str:
    """Concatenate text from a spread of pages (start, middle, end)."""
    count = document.page_count
    picks: list[int] = []
    picks.extend(range(min(limit // 2, count)))
    picks.extend(range(max(count - limit // 2, 0), count))
    parts = []
    for index in sorted(set(picks)):
        parts.append(document.load_page(index).get_text("text"))  # type: ignore[no-untyped-call]
    return "\n".join(parts)


def _measure_page(page: pymupdf.Page, page_number: int) -> PageInspection:
    """Collect per-page facts; never raises (corrupt pages are flagged)."""
    entry = PageInspection(page_number=page_number)
    try:
        text = page.get_text("text")  # type: ignore[no-untyped-call]
        chars = len(text)
        entry.chars = chars
        entry.text_selectable = chars > 0
        entry.density = density_band(chars)
        entry.has_images = bool(page.get_images(full=True))  # type: ignore[no-untyped-call]
    except Exception as exc:
        entry.error = f"unreadable page: {exc}"
        return entry
    # A page is "scanned" when it is an image render with no reusable text.
    if entry.text_selectable and entry.chars >= TEXT_MIN_CHARS:
        entry.scanned = False
    elif entry.has_images:
        entry.scanned = True
    else:
        entry.scanned = False
    return entry


def _classify(page_count: int, text_pages: int, scanned_pages: int) -> PdfClassification:
    if page_count <= 0:
        return PdfClassification.INVALID_PDF
    text_ratio = text_pages / page_count
    scanned_ratio = scanned_pages / page_count
    if scanned_ratio >= SCANNED_RATIO or text_pages == 0:
        return PdfClassification.SCANNED_PDF
    if text_ratio >= TEXT_RATIO and scanned_ratio <= SCANNED_TOLERANCE:
        return PdfClassification.TEXT_PDF
    return PdfClassification.MIXED_PDF


def inspect_file(
    source_file: SourceFile,
    *,
    session: Session,
    report_dir: Path,
    data_dir: Path,
) -> InspectionResult:
    """Classify ``source_file`` and write its inspection report + job record."""
    result = InspectionResult(
        sha256=source_file.sha256,
        source_file_id=str(source_file.id),
    )
    path = data_dir.resolve() / source_file.file_path
    report_dir = report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    if not path.is_file():
        result.error = f"file not found: {path}"
        result.classification = PdfClassification.INVALID_PDF
        _write_reports(result, report_dir)
        _upsert_job(session, result)
        return result

    result.file_size = path.stat().st_size

    try:
        document = pymupdf.open(str(path))  # type: ignore[no-untyped-call]
    except Exception as exc:
        result.error = f"cannot open pdf: {exc}"
        result.classification = PdfClassification.INVALID_PDF
        result.corruption_flags.append("cannot_open")
        _write_reports(result, report_dir)
        _upsert_job(session, result)
        return result

    with document:
        try:
            result.page_count = document.page_count
            result.encrypted = bool(document.needs_pass)
            result.is_repaired = bool(document.is_repaired)
        except Exception as exc:
            result.error = f"pdf header unreadable: {exc}"
            result.classification = PdfClassification.INVALID_PDF
            result.corruption_flags.append("header_unreadable")
            _write_reports(result, report_dir)
            _upsert_job(session, result)
            return result

        if result.is_repaired:
            result.corruption_flags.append("repaired")

        try:
            metadata = dict(document.metadata or {})
            result.pdf_meta = {key: str(value) for key, value in metadata.items() if value}
            result.pdf_version = document.pdf_version  # type: ignore[attr-defined]
        except Exception:
            result.corruption_flags.append("metadata_unreadable")

        if not result.encrypted:
            result.pages = []
            for index in range(result.page_count):
                try:
                    page = document.load_page(index)  # type: ignore[no-untyped-call]
                except Exception as exc:
                    entry = PageInspection(page_number=index + 1)
                    entry.error = f"cannot load page: {exc}"
                    result.unreadable_pages += 1
                    result.pages.append(entry)
                    continue
                entry = _measure_page(page, index + 1)
                if entry.error is not None:
                    result.unreadable_pages += 1
                    result.corruption_flags.append("unreadable_page")
                result.pages.append(entry)
            result.text_pages = sum(1 for p in result.pages if p.chars >= TEXT_MIN_CHARS)
            result.scanned_pages = sum(1 for p in result.pages if p.scanned)
            result.blank_pages = sum(
                1 for p in result.pages if p.chars == 0 and not p.has_images and not p.scanned
            )
            result.chars_total = sum(p.chars for p in result.pages)
            sample = _sample_text(document)
            result.language_hint = detect_script_hint(sample)
        else:
            result.corruption_flags.append("encrypted_pdf")

    scanned_ratio = (result.scanned_pages / result.page_count) if result.page_count else 1.0
    unreadable_ratio = (result.unreadable_pages / result.page_count) if result.page_count else 1.0
    if (
        result.error is not None
        or result.encrypted
        or result.page_count == 0
        or (result.unreadable_pages > 5 and unreadable_ratio > 0.5)
    ):
        result.classification = PdfClassification.INVALID_PDF
    else:
        result.classification = _classify(
            result.page_count, result.text_pages, result.scanned_pages
        )
    result.ocr_likely = result.classification in (
        PdfClassification.MIXED_PDF,
        PdfClassification.SCANNED_PDF,
    )
    if scanned_ratio > WARNING_SCANNED_RATIO:
        result.corruption_flags.append("scanned_page_present")

    _write_reports(result, report_dir)
    _upsert_job(session, result)
    return result


def _write_reports(result: InspectionResult, report_dir: Path) -> None:
    json_path = report_dir / f"{result.sha256}.json"
    json_path.write_text(
        json.dumps(_report_dict(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result.report_path = json_path
    summary_path = report_dir / f"{result.sha256}.txt"
    summary_path.write_text(_human_summary(result), encoding="utf-8")
    result.summary_path = summary_path


def _report_dict(result: InspectionResult) -> dict[str, object]:
    return {
        "source": {
            "sha256": result.sha256,
            "source_file_id": result.source_file_id,
            "file_size": result.file_size,
        },
        "pdf": {
            "page_count": result.page_count,
            "encrypted": result.encrypted,
            "pdf_version": result.pdf_version,
            "is_repaired": result.is_repaired,
            "corruption_flags": result.corruption_flags,
            "metadata": result.pdf_meta,
        },
        "classification": result.classification.value,
        "pages": {
            "total": result.page_count,
            "text": result.text_pages,
            "scanned": result.scanned_pages,
            "blank": result.blank_pages,
            "unreadable": result.unreadable_pages,
            "chars_total": result.chars_total,
            "detail": [p.as_dict() for p in result.pages],
        },
        "language": {"hint": result.language_hint},
        "ocr_likely": result.ocr_likely,
        "error": result.error,
        "inspected_at": datetime.now(UTC).isoformat(),
    }


def _human_summary(result: InspectionResult) -> str:
    file_name = _file_name(result.sha256)
    lines = [
        file_name,
        "",
        f"File size: {result.file_size or 0} bytes",
        f"Pages: {result.page_count}",
        f"Text pages: {result.text_pages}",
        f"Scanned pages: {result.scanned_pages}",
        f"Blank pages: {result.blank_pages}",
        f"Classification: {result.classification.value.upper()}",
        f"Language hint: {result.language_hint or 'unknown'}",
        f"Encrypted: {'yes' if result.encrypted else 'no'}",
    ]
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.corruption_flags:
        lines.append(f"Corruption indicators: {', '.join(result.corruption_flags)}")
    return "\n".join(lines) + "\n"


def _file_name(sha256: str) -> str:
    return f"{sha256[:12]}.pdf"


def _upsert_job(session: Session, result: InspectionResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    manifest = {
        "page_count": result.page_count,
        "file_size": result.file_size,
        "text_pages": result.text_pages,
        "scanned_pages": result.scanned_pages,
        "blank_pages": result.blank_pages,
        "unreadable_pages": result.unreadable_pages,
        "chars_total": result.chars_total,
        "encrypted": result.encrypted,
        "classification": result.classification.value,
        "ocr_likely": result.ocr_likely,
        "language_hint": result.language_hint,
        "corruption_flags": result.corruption_flags,
        "report": result.report_path.name if result.report_path else None,
    }
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.INSPECT,
        status=status,
        manifest=manifest,
        error=result.error,
    )


def inspect_all(
    session: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
) -> list[InspectionResult]:
    """Inspect every registered source file (optionally limited)."""
    if settings is None:
        settings = get_settings()
    report_dir = settings.data_dir / "processed" / "inspect"
    sources = session.scalars(
        select(SourceFile).order_by(SourceFile.created_at)
    ).all()
    if limit is not None:
        sources = sources[:limit]

    results: list[InspectionResult] = []
    for source in sources:
        logger.info("inspecting {}", source.sha256[:12])
        results.append(
            inspect_file(
                source,
                session=session,
                report_dir=report_dir,
                data_dir=settings.data_dir,
            )
        )
    return results


__all__ = [
    "InspectionResult",
    "PageInspection",
    "PdfClassification",
    "density_band",
    "detect_script_hint",
    "inspect_all",
    "inspect_file",
]