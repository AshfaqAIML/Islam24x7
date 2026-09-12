"""Text extraction: pull page-by-page text from PDFs that have a text layer.

Only pages that actually contain extractable text produce output files;
blank/scanned pages are recorded in the index with ``chars == 0`` and no
file, so later stages know exactly which pages need OCR.

Output layout::

    data/processed/extract/<sha256>/pages/0001.txt
    data/processed/extract/<sha256>/index.json

Extracted text is the verbatim document text — never normalized here.
"""

from __future__ import annotations

import json
import shutil
import uuid
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
from knowledge_base.pipeline.jobs import upsert_processing_job


@dataclass
class PageExtract:
    """One page's extracted text result."""

    page_number: int
    chars: int
    quality: str = "blank"
    file_name: str | None = None


@dataclass
class ExtractResult:
    """Outcome of extracting one source file."""

    sha256: str
    source_file_id: str
    page_count: int = 0
    pages_with_text: int = 0
    pages_ok: int = 0
    pages_garbled: int = 0
    chars_total: int = 0
    output_dir: Path | None = None
    error: str | None = None
    pages: list[PageExtract] = field(default_factory=list)


def _classify(text: str) -> str:
    """Return 'ok', 'garbled', or 'blank' for an extracted page.

    A page is garbled when the PDF text layer exists but its glyphs don't
    map to clean Unicode (the classic Arabic/Urdu PDF problem), i.e. few
    actual letters or mostly ``?`` replacement glyphs.
    """
    chars = [ch for ch in text if not ch.isspace()]
    total = len(chars)
    if total == 0:
        return "blank"
    letters = sum(1 for ch in chars if ch.isalpha())
    questions = sum(1 for ch in chars if ch == "?")
    if letters / total < 0.5 or questions / total > 0.3:
        return "garbled"
    return "ok"


def extract_file(
    source_file: SourceFile,
    *,
    session: Session,
    output_dir: Path,
    data_dir: Path,
) -> ExtractResult:
    """Extract page text for ``source_file``, writing files + job record."""
    result = ExtractResult(
        sha256=source_file.sha256,
        source_file_id=str(source_file.id),
    )
    path = data_dir.resolve() / source_file.file_path
    output_dir = output_dir.resolve()
    pages_dir = output_dir / "pages"

    try:
        document = pymupdf.open(str(path))  # type: ignore[no-untyped-call]
    except Exception as exc:
        result.error = f"cannot open pdf: {exc}"
        _finish(result, session, output_dir)
        return result

    with document:
        if document.needs_pass:
            result.error = "pdf is encrypted"
            _finish(result, session, output_dir)
            return result

        result.page_count = document.page_count
        if pages_dir.exists():
            shutil.rmtree(pages_dir)
        pages_dir.mkdir(parents=True, exist_ok=True)
        for index in range(result.page_count):
            text = document.load_page(index).get_text("text")  # type: ignore[no-untyped-call]
            quality = _classify(text)
            page = PageExtract(page_number=index + 1, chars=len(text), quality=quality)
            if quality == "ok":
                file_name = f"{index + 1:04d}.txt"
                (pages_dir / file_name).write_text(text, encoding="utf-8")
                page.file_name = file_name
                result.pages_ok += 1
            elif quality == "garbled":
                result.pages_garbled += 1
            if quality != "blank":
                result.pages_with_text += 1
                result.chars_total += len(text)
            result.pages.append(page)

    _finish(result, session, output_dir)
    return result


def _finish(
    result: ExtractResult,
    session: Session,
    output_dir: Path,
) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    data = {
        "source": {"sha256": result.sha256, "source_file_id": result.source_file_id},
        "pages": {
            "total": result.page_count,
            "with_text": result.pages_with_text,
            "ok": result.pages_ok,
            "garbled": result.pages_garbled,
            "chars_total": result.chars_total,
        },
        "error": result.error,
        "extracted_at": datetime.now(UTC).isoformat(),
        "page_files": [
            {
                "page": p.page_number,
                "chars": p.chars,
                "quality": p.quality,
                "file": p.file_name,
            }
            for p in result.pages
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    result.output_dir = output_dir

    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.EXTRACT,
        status=status,
        manifest={
            "page_count": result.page_count,
            "pages_with_text": result.pages_with_text,
            "pages_ok": result.pages_ok,
            "pages_garbled": result.pages_garbled,
            "chars_total": result.chars_total,
        },
        error=result.error,
    )


def _has_extractable_text(session: Session, source_file_id: str) -> bool:
    job = session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source_file_id,
            ProcessingJob.job_type == JobType.INSPECT,
        )
    )
    if job is None:
        return True
    return bool(job.manifest.get("pages_with_text", 0) > 0)


def extract_all(
    session: Session,
    *,
    settings: Settings | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[ExtractResult]:
    """Extract every registered PDF with a text layer (unless ``force``)."""
    if settings is None:
        settings = get_settings()
    output_root = settings.data_dir / "processed" / "extract"
    sources = session.scalars(select(SourceFile).order_by(SourceFile.created_at)).all()
    if limit is not None:
        sources = sources[:limit]

    results: list[ExtractResult] = []
    for source in sources:
        if not force and not _has_extractable_text(session, str(source.id)):
            logger.info("skipping {} (no text layer)", source.sha256[:12])
            continue
        logger.info("extracting {}", source.sha256[:12])
        results.append(
            extract_file(
                source,
                session=session,
                output_dir=output_root / source.sha256,
                data_dir=settings.data_dir,
            )
        )
    return results


__all__ = ["ExtractResult", "extract_all", "extract_file"]