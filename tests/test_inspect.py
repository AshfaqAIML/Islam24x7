"""Tests for the PDF inspection stage."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import JobType, PdfClassification, SourceFormat
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.pipeline.ingest.ingest import ingest_directory
from knowledge_base.pipeline.inspect.inspect import (
    density_band,
    detect_script_hint,
    inspect_file,
)


def _make_pdf(dirpath: Path, *, text_pages: list[str], blank_pages: int = 0) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "sample.pdf"
    doc = pymupdf.open()
    for text in text_pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=24)
    for _ in range(blank_pages):
        doc.new_page()
    doc.save(path)
    doc.close()
    return path


def _make_scanned_pdf(dirpath: Path, *, pages: int) -> Path:
    """A PDF whose pages are images with no text layer."""
    dirpath.mkdir(parents=True, exist_ok=True)
    image_path = dirpath / "tile.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 120))
    pix.clear_with(220)  # type: ignore[no-untyped-call]
    pix.save(image_path)
    path = dirpath / "scanned.pdf"
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_image(page.rect, filename=str(image_path))  # type: ignore[no-untyped-call]
    doc.save(path)
    doc.close()
    return path


def _ingested_source(db: Session, data_dir: Path, source_file: Path) -> SourceFile:
    ingest_directory(source_file.parent, session=db, data_dir=data_dir)
    db.commit()
    source = db.scalar(select(SourceFile))
    assert source is not None
    return source


def _inspect(
    db: Session, data_dir: Path, pdf: Path, *, report_dir: Path | None = None
):
    source = _ingested_source(db, data_dir, pdf)
    return inspect_file(
        source,
        session=db,
        report_dir=report_dir or (data_dir / "processed" / "inspect"),
        data_dir=data_dir,
    )


def test_detect_script_hint() -> None:
    assert detect_script_hint("بِسْمِ اللهِ الرَّحْمَنِ الرَّحِيمِ") == "ar"
    assert detect_script_hint("بھی یہ ہے ڈ اور گ") == "ur"
    assert detect_script_hint("plain english text") == "en"
    assert detect_script_hint("1234567890") is None
    assert detect_script_hint("") is None


def test_density_band() -> None:
    assert density_band(0) == "none"
    assert density_band(10) == "low"
    assert density_band(500) == "medium"
    assert density_band(5000) == "high"


def test_inspect_text_pdf_metadata_size_and_report(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    long_text = "The quick brown fox jumps over the lazy dog while students study hadith."
    pdf = _make_pdf(tmp_path / "src", text_pages=[long_text, long_text])
    result = _inspect(db, data_dir, pdf)

    assert result.error is None
    assert result.classification == PdfClassification.TEXT_PDF
    assert result.page_count == 2
    assert result.text_pages == 2
    assert result.scanned_pages == 0
    assert result.blank_pages == 0
    assert result.file_size == pdf.stat().st_size
    assert result.file_size is not None and result.file_size > 0
    assert result.ocr_likely is False
    assert result.language_hint == "en"
    assert result.pages[0].density == "low"
    assert result.pages[0].text_selectable is True
    assert result.pages[0].scanned is False
    assert result.pages[0].has_images is False

    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["classification"] == "text_pdf"
    assert report["pdf"]["metadata"] is not None
    assert report["pages"]["total"] == 2
    assert report["pages"]["detail"][0]["density"] == "low"

    summary = result.summary_path.read_text(encoding="utf-8")
    assert "Pages: 2" in summary
    assert "Text pages: 2" in summary
    assert "Classification: TEXT_PDF" in summary


def test_inspect_scanned_pdf(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_scanned_pdf(tmp_path / "src", pages=4)
    result = _inspect(db, data_dir, pdf)

    assert result.error is None
    assert result.classification == PdfClassification.SCANNED_PDF
    assert result.page_count == 4
    assert result.text_pages == 0
    assert result.scanned_pages == 4
    assert result.ocr_likely is True
    assert all(p.scanned for p in result.pages)
    assert all(p.has_images for p in result.pages)
    assert result.language_hint is None


def test_inspect_mixed_pdf(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    scan_dir = tmp_path / "scan"
    scanned = _make_scanned_pdf(scan_dir, pages=2)
    text_dir = tmp_path / "src"
    long_text = "A proper text page carries enough letters to count as selectable text."
    text_pdf = _make_pdf(text_dir, text_pages=[long_text], blank_pages=0)

    # One file = two scanned pages + one text page, placed in its own dir
    # so ingestion registers exactly one source.
    merged_dir = tmp_path / "mixed"
    merged_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    scan_src = pymupdf.open(str(scanned))
    doc.insert_pdf(scan_src)
    text_src = pymupdf.open(str(text_pdf))
    doc.insert_pdf(text_src)
    scan_src.close()
    text_src.close()
    merged_path = merged_dir / "mixed.pdf"
    doc.save(merged_path)
    doc.close()

    result = _inspect(db, data_dir, merged_path)

    assert result.page_count == 3
    assert result.text_pages == 1
    assert result.scanned_pages == 2
    assert result.blank_pages == 0
    assert result.classification == PdfClassification.MIXED_PDF
    assert result.ocr_likely is True


def test_inspect_all_blank_pages_is_scanned(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=[], blank_pages=3)
    result = _inspect(db, data_dir, pdf)

    assert result.page_count == 3
    assert result.text_pages == 0
    assert result.scanned_pages == 0
    assert result.blank_pages == 3
    assert result.classification == PdfClassification.SCANNED_PDF


def test_inspect_missing_file_is_invalid(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    source = SourceFile(
        sha256="9" * 64,
        file_path="does-not-exist.pdf",
        format=SourceFormat.PDF,
    )
    db.add(source)
    db.commit()

    result = inspect_file(
        source, session=db, report_dir=tmp_path / "processed", data_dir=data_dir
    )

    assert result.error is not None
    assert "file not found" in result.error
    assert result.classification == PdfClassification.INVALID_PDF
    db.commit()
    job = db.scalar(select(ProcessingJob))
    assert job is not None and job.status == "failed"
    assert job.manifest["classification"] == "invalid_pdf"


def test_inspect_corrupt_file_is_invalid(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = tmp_path / "src" / "broken.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4 this is not a real pdf" * 3)
    source = _ingested_source(db, data_dir, pdf)

    result = inspect_file(
        source, session=db, report_dir=data_dir / "processed" / "inspect", data_dir=data_dir
    )

    assert result.error is not None
    assert result.classification == PdfClassification.INVALID_PDF
    assert "cannot_open" in result.corruption_flags


def test_inspect_language_hint_from_sampled_pages(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    page_text = "The scholars transmitted the hadith with care across many generations."
    pdf = _make_pdf(tmp_path / "src", text_pages=[page_text, page_text])
    result = _inspect(db, data_dir, pdf)

    assert result.language_hint == "en"
    assert result.classification == PdfClassification.TEXT_PDF


def test_inspect_writes_job_with_classification(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(
        tmp_path / "src",
        text_pages=["Hello world, this is certainly a text page for the test."],
    )
    result = _inspect(db, data_dir, pdf)
    db.commit()

    job = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.job_type == JobType.INSPECT,
            ProcessingJob.source_file_id == result.source_file_id,
        )
    )
    assert job is not None
    assert job.status == "succeeded"
    assert job.manifest["classification"] == "text_pdf"
    assert job.manifest["text_pages"] == 1
    assert job.manifest["file_size"] == pdf.stat().st_size


def test_inspect_repeat_is_idempotent(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Repeat"])
    source = _ingested_source(db, data_dir, pdf)
    report_dir = data_dir / "processed" / "inspect"

    inspect_file(source, session=db, report_dir=report_dir, data_dir=data_dir)
    db.commit()
    inspect_file(source, session=db, report_dir=report_dir, data_dir=data_dir)
    db.commit()

    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.job_type == JobType.INSPECT)).all()
    assert len(jobs) == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("النَّهْر", "ar"),
        ("Urdu یہی ہے", "ur"),
        ("English only", "en"),
        ("", None),
    ],
)
def test_detect_script_hint_parametrized(text: str, expected: str | None) -> None:
    assert detect_script_hint(text) == expected