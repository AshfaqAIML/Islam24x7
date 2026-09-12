"""PDF inspection: classify a source file's text layer.

Reads a stored PDF with PyMuPDF (never rendering images) and determines:

- page count and same
- how many pages carry extractable text (text layer vs scanned images)
- script/language hint (Arabic vs Latin) from a sampled page spread
- whether OCR will likely be required (``ocr_likely``)

Writes a per-page report to ``data/processed/inspect/<category>/<sha>/`` and
records a ``ProcessingJob`` of type ``inspect``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import JobStatus, JobType
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.logging import logger

_ARABIC_RANGES = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)
_URDU_EXTRA = {0x06BE, 0x06BA, 0x06D2, 0x06CC, 0x0679, 0x0688, 0x06AF, 0x06C1}


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


@dataclass
class InspectionResult:
    """Summary of one inspected PDF."""

    sha256: str
    source_file_id: str
    page_count: int = 0
    pages_with_text: int = 0
    chars_total: int = 0
    encrypted: bool = False
    ocr_likely: bool = False
    language_hint: str | None = None
    report_path: Path | None = None
    error: str | None = None
    pdf_meta: dict[str, str | int] = field(default_factory=dict)


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

    try:
        document = pymupdf.open(str(path))  # type: ignore[no-untyped-call]
    except Exception as exc:
        result.error = f"cannot open pdf: {exc}"
        _write_report(result, report_dir)
        _upsert_job(session, result, report_dir)
        return result

    with document:
        result.page_count = document.page_count
        result.encrypted = bool(document.needs_pass)
        if document.metadata:
            result.pdf_meta = {
                key: str(value) for key, value in document.metadata.items() if value
            }

        if not result.encrypted:
            chars_by_page: list[int] = []
            for index in range(result.page_count):
                text = document.load_page(index).get_text("text")  # type: ignore[no-untyped-call]
                chars_by_page.append(len(text))
                result.chars_total += len(text)
            result.pages_with_text = sum(1 for n in chars_by_page if n > 0)
            sample = _sample_text(document)
            result.language_hint = detect_script_hint(sample)
            if result.page_count:
                result.ocr_likely = result.pages_with_text / result.page_count < 0.5
        else:
            chars_by_page = []

        _write_report(result, report_dir, chars_by_page=chars_by_page)
    _upsert_job(session, result, report_dir)
    return result


def _write_report(
    result: InspectionResult,
    report_dir: Path,
    chars_by_page: list[int] | None = None,
) -> None:
    data = {
        "source": {
            "sha256": result.sha256,
            "source_file_id": result.source_file_id,
        },
        "pdf": {
            "page_count": result.page_count,
            "encrypted": result.encrypted,
            "metadata": result.pdf_meta,
        },
        "text": {
            "pages_with_text": result.pages_with_text,
            "chars_total": result.chars_total,
            "chars_by_page": chars_by_page or [],
        },
        "language": {"hint": result.language_hint},
        "ocr_likely": result.ocr_likely,
        "error": result.error,
        "inspected_at": datetime.now(UTC).isoformat(),
    }
    report_path = report_dir / f"{result.sha256}.json"
    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    result.report_path = report_path


def _upsert_job(session: Session, result: InspectionResult, report_dir: Path) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    manifest = {
        "page_count": result.page_count,
        "pages_with_text": result.pages_with_text,
        "chars_total": result.chars_total,
        "encrypted": result.encrypted,
        "ocr_likely": result.ocr_likely,
        "language_hint": result.language_hint,
        "report": report_dir.name if result.report_path else None,
    }
    job = session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == result.source_file_id,
            ProcessingJob.job_type == JobType.INSPECT,
        )
    )
    if job is None:
        job = ProcessingJob(
            source_file_id=result.source_file_id,
            job_type=JobType.INSPECT,
            status=status,
            manifest=manifest,
        )
        session.add(job)
    else:
        job.status = status
        job.manifest = manifest
        job.error = result.error


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
    "detect_script_hint",
    "inspect_all",
    "inspect_file",
]