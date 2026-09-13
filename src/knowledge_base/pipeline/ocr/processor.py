"""OCR processor for scanned / garbled pages of the library.

Responsibilities (matching the OCR pipeline spec):

1. **Detect** pages that require OCR — from the stored *inspect* page scan
   flags (``scanned``) and *extract* quality flags (``garbled``), falling
   back to "every page" when no prior stage artifacts exist at all.
2. **Render only the required pages** to PNG (images are kept separate).
3. **OCR page-by-page**, preserving original PDF page numbers.
4. Store OCR text **separately from the rendered images** (``text/`` vs
   ``render/``) — the source PDF is never opened for writing.
5. Record engine/version, status, and confidence where the backend exposes
   it (``ocr_pages`` table + ``ProcessingJob`` manifest).
6. **Flag suspicious output for review** (low confidence, very short text,
   symbol-heavy text, empty result) — output is never fabricated, padded,
   or silently corrected.

Layout under ``data/processed/ocr/<sha256>/``::

    render/<page>.png   rendered page images (only pages that needed OCR)
    text/<page>.txt     verbatim OCR text
    report.json         machine-readable per-page quality report
    report.txt          human-readable summary
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
from knowledge_base.database.enums import JobStatus, JobType, OcrStatus
from knowledge_base.database.models.ocr import OcrPage
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.logging import logger
from knowledge_base.pipeline.jobs import upsert_processing_job
from knowledge_base.pipeline.ocr.config import OcrConfig
from knowledge_base.pipeline.ocr.engines import OcrEngine, OcrSnippet

_PAGE_NO = "{0:04d}"
_EMPTY_SNIPPET_QUALITY_NOTES = "no_text"


def density_chars(text: str) -> int:
    """Count non-whitespace characters (a compact text-size proxy)."""
    return sum(1 for ch in text if not ch.isspace())


def assess_quality(snippet: OcrSnippet, config: OcrConfig) -> tuple[OcrStatus, list[str]]:
    """Classify one OCR snippet as ``ok`` or ``review`` with human-readable notes.

    ``text`` is never modified here — we only decide whether to ask a human
    to look at it. Empty/very short/symbol-heavy results go to review rather
    than being replaced by a guess.
    """
    reasons: list[str] = []
    text = snippet.text.strip()
    if not text:
        reasons.append(_EMPTY_SNIPPET_QUALITY_NOTES)
        return OcrStatus.REVIEW, reasons
    if snippet.confidence is not None and snippet.confidence < config.min_confidence:
        reasons.append(f"low_confidence={snippet.confidence:.1f}")
    chars = density_chars(text)
    if chars < config.min_text_chars:
        reasons.append(f"very_short_text={chars}")
    letters = sum(1 for ch in text if ch.isalpha())
    if chars and letters / chars < config.min_alpha_ratio:
        reasons.append(f"low_alpha_ratio={letters / chars:.2f}")
    return (OcrStatus.REVIEW if reasons else OcrStatus.OK), reasons


@dataclass
class OcrResult:
    """Outcome of processing one source file."""

    sha256: str
    source_file_id: str
    engine: str
    engine_version: str
    languages: tuple[str, ...]
    page_count: int = 0
    pages_required: int = 0
    pages_ocr: int = 0
    pages_skipped: int = 0
    pages_review: int = 0
    pages_failed: int = 0
    avg_confidence: float | None = None
    output_dir: Path | None = None
    error: str | None = None
    pages: list[dict[str, object]] = field(default_factory=list)


def _root_dir(data_dir: Path) -> Path:
    return data_dir.resolve()


def _out_dir(data_dir: Path, sha256: str) -> Path:
    return _root_dir(data_dir) / "processed" / "ocr" / sha256


def plan_ocr_pages(source_file: SourceFile, data_dir: Path) -> tuple[list[int], int]:
    """Return ``(required_page_numbers, total_pages)``.

    Sources of truth, in order:

    1. ``inspect/<sha>.json`` — pages flagged ``scanned`` need OCR.
    2. ``extract/<sha>/index.json`` — pages whose text layer was ``garbled``
       (present but unmappable to Unicode) need OCR.
    3. No signal from either stage -> every page needs OCR (safe default).
    """
    root = _root_dir(data_dir)
    needed: set[int] = set()
    page_count: int | None = None
    saw_signal = False

    inspect_path = root / "processed" / "inspect" / f"{source_file.sha256}.json"
    if inspect_path.is_file():
        saw_signal = True
        report = json.loads(inspect_path.read_text(encoding="utf-8"))
        page_count = int(report.get("pdf", {}).get("page_count", 0))
        for page in report.get("pages", {}).get("detail", []):
            if page.get("scanned"):
                needed.add(int(page["page"]))

    extract_path = root / "processed" / "extract" / source_file.sha256 / "index.json"
    if extract_path.is_file():
        saw_signal = True
        index = json.loads(extract_path.read_text(encoding="utf-8"))
        if page_count is None:
            page_count = int(index.get("pages", {}).get("total", 0))
        for page in index.get("page_files", []):
            # Any page without an extracted text file needs OCR: garbled
            # glyphs, scanned pages, and blank leaves alike. We prefer to
            # render one unnecessary blank page over silently losing content.
            if not page.get("file"):
                needed.add(int(page["page"]))

    if page_count is None:
        document = _open_strict(root / source_file.file_path)
        if document is None:
            return [], 0
        with document:
            page_count = document.page_count

    if not needed and not saw_signal:
        needed = set(range(1, page_count + 1))
    return sorted(needed), page_count


def _open_strict(path: Path) -> pymupdf.Document | None:
    try:
        return pymupdf.open(str(path))  # type: ignore[no-untyped-call]
    except Exception:
        return None


def _render_page(document: pymupdf.Document, page_number: int, dpi: int, png_path: Path) -> None:
    page = document.load_page(page_number - 1)  # type: ignore[no-untyped-call]
    pixmap = page.get_pixmap(dpi=dpi)
    pixmap.save(str(png_path))


def ocr_file(
    source_file: SourceFile,
    *,
    session: Session,
    engine: OcrEngine,
    config: OcrConfig,
    data_dir: Path,
    force: bool = False,
) -> OcrResult:
    """Run OCR over the pages that need it and record everything."""
    result = OcrResult(
        sha256=source_file.sha256,
        source_file_id=str(source_file.id),
        engine=engine.name,
        engine_version=engine.version,
        languages=config.languages,
    )
    root = _root_dir(data_dir)
    out = _out_dir(root, source_file.sha256)
    render_dir = out / "render"
    text_dir = out / "text"
    pdf_path = root / source_file.file_path

    document = _open_strict(pdf_path)
    if document is None:
        result.error = f"cannot open pdf: {pdf_path}"
        _finish(result, session, out, config)
        return result
    if document.needs_pass:
        result.error = "pdf is encrypted"
        _finish(result, session, out, config)
        return result

    required, total = plan_ocr_pages(source_file, root)
    result.page_count = total
    result.pages_required = len(required)

    existing = {
        row.page_number: row
        for row in session.scalars(select(OcrPage).where(OcrPage.source_file_id == source_file.id))
    }

    render_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    confidences: list[float] = []

    with document:
        for page_number in required:
            if page_number in existing and not force:
                result.pages_skipped += 1
                row = existing[page_number]
                if row.confidence is not None:
                    confidences.append(row.confidence)
                _append_page_result(result, row)
                continue

            page_image = render_dir / f"{_PAGE_NO.format(page_number)}.png"
            try:
                _render_page(document, page_number, config.dpi, page_image)
            except Exception as exc:
                row = _persist_page(
                    session,
                    source_file.id,
                    page_number,
                    engine,
                    config,
                    OcrStatus.FAILED,
                    confidence=None,
                    quality_notes=None,
                    text_chars=0,
                    text_path=None,
                    image_path=_rel(root, page_image),
                    error=f"render failed: {exc}",
                    existing=existing.get(page_number),
                )
                result.pages_failed += 1
                _append_page_result(result, row)
                session.commit()
                continue

            try:
                snippet = engine.ocr_image(page_image, config.languages)
            except Exception as exc:
                row = _persist_page(
                    session,
                    source_file.id,
                    page_number,
                    engine,
                    config,
                    OcrStatus.FAILED,
                    confidence=None,
                    quality_notes=None,
                    text_chars=0,
                    text_path=None,
                    image_path=_rel(root, page_image),
                    error=f"ocr failed: {exc}",
                    existing=existing.get(page_number),
                )
                result.pages_failed += 1
                _append_page_result(result, row)
                session.commit()
                continue

            page_text = text_dir / f"{_PAGE_NO.format(page_number)}.txt"
            status, notes = assess_quality(snippet, config)
            page_text.write_text(snippet.text, encoding="utf-8")
            row = _persist_page(
                session,
                source_file.id,
                page_number,
                engine,
                config,
                status,
                confidence=snippet.confidence,
                quality_notes=", ".join(notes) or None,
                text_chars=density_chars(snippet.text),
                text_path=_rel(root, page_text),
                image_path=_rel(root, page_image),
                existing=existing.get(page_number),
            )
            result.pages_ocr += 1
            if status == OcrStatus.REVIEW:
                result.pages_review += 1
            if snippet.confidence is not None:
                confidences.append(snippet.confidence)
            _append_page_result(result, row)

            session.commit()

    if confidences:
        result.avg_confidence = sum(confidences) / len(confidences)
    _finish(result, session, out, config)
    return result


def _finish(
    result: OcrResult,
    session: Session,
    out: Path,
    config: OcrConfig,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = {
        "source": {"sha256": result.sha256, "source_file_id": result.source_file_id},
        "engine": {"name": result.engine, "version": result.engine_version},
        "languages": list(result.languages),
        "pages": {
            "total": result.page_count,
            "required": result.pages_required,
            "ocr": result.pages_ocr,
            "skipped": result.pages_skipped,
            "review": result.pages_review,
            "failed": result.pages_failed,
            "avg_confidence": result.avg_confidence,
            "detail": result.pages,
        },
        "error": result.error,
        "processed_at": datetime.now(UTC).isoformat(),
    }
    (out / "report.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result.output_dir = out

    review_pages = [str(p["page"]) for p in result.pages if p["status"] == "review"]
    lines = [
        f"{result.sha256[:12]}.pdf",
        "",
        f"Engine: {result.engine} {result.engine_version}",
        f"Languages: {'+'.join(result.languages)}",
        f"Pages: {result.page_count}",
        f"OCR pages: {result.pages_ocr}",
        f"Review pages: {result.pages_review}",
        f"Failed pages: {result.pages_failed}",
        (
            f"Avg confidence: {result.avg_confidence:.1f}"
            if result.avg_confidence is not None
            else "Avg confidence: n/a"
        ),
    ]
    if review_pages:
        lines.append(f"Review page numbers: {', '.join(review_pages)}")
    if result.error:
        lines.append(f"Error: {result.error}")
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _upsert_job(session, result)


def _upsert_job(session: Session, result: OcrResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.OCR,
        status=status,
        manifest={
            "engine": result.engine,
            "engine_version": result.engine_version,
            "languages": list(result.languages),
            "pages_total": result.page_count,
            "pages_required": result.pages_required,
            "pages_ocr": result.pages_ocr,
            "pages_skipped": result.pages_skipped,
            "pages_review": result.pages_review,
            "pages_failed": result.pages_failed,
            "avg_confidence": result.avg_confidence,
        },
        error=result.error,
    )


def _persist_page(
    session: Session,
    source_file_id: uuid.UUID,
    page_number: int,
    engine: OcrEngine,
    config: OcrConfig,
    status: OcrStatus,
    *,
    confidence: float | None,
    quality_notes: str | None,
    text_chars: int,
    text_path: str | None,
    image_path: str | None,
    error: str | None = None,
    existing: OcrPage | None = None,
) -> OcrPage:
    language_str = "+".join(config.languages) if config.languages else None
    row = existing
    if row is None:
        row = OcrPage(
            source_file_id=source_file_id,
            page_number=page_number,
            engine=engine.name,
            engine_version=engine.version,
            languages=language_str,
        )
        session.add(row)
    else:
        row.engine = engine.name
        row.engine_version = engine.version
        row.languages = language_str
    row.status = status
    row.confidence = confidence
    row.quality_notes = quality_notes
    row.text_chars = text_chars
    row.text_path = text_path
    row.image_path = image_path
    row.error = error
    return row


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def _append_page_result(result: OcrResult, row: OcrPage) -> None:
    result.pages.append(
        {
            "page": row.page_number,
            "status": row.status.value,
            "engine": row.engine,
            "engine_version": row.engine_version,
            "confidence": row.confidence,
            "text_chars": row.text_chars,
            "quality_notes": row.quality_notes,
            "text": row.text_path,
            "image": row.image_path,
            "error": row.error,
        }
    )


def ocr_all(
    session: Session,
    *,
    settings: Settings | None = None,
    engine: OcrEngine | None = None,
    config: OcrConfig | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[OcrResult]:
    """OCR every registered source file that needs it."""
    if settings is None:
        settings = get_settings()
    if config is None:
        config = OcrConfig()
    if engine is None:
        from knowledge_base.pipeline.ocr.engines import build_engine

        engine = build_engine(config.engine, config)
    sources = session.scalars(select(SourceFile).order_by(SourceFile.created_at)).all()
    if limit is not None:
        sources = sources[:limit]

    results: list[OcrResult] = []
    for source in sources:
        logger.info("ocr {} (engine {})", source.sha256[:12], engine.name)
        results.append(
            ocr_file(
                source,
                session=session,
                engine=engine,
                config=config,
                data_dir=settings.data_dir,
                force=force,
            )
        )
    return results


__all__ = [
    "OcrResult",
    "assess_quality",
    "density_chars",
    "ocr_all",
    "ocr_file",
    "plan_ocr_pages",
]
