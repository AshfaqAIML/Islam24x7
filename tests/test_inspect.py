"""Tests for the PDF inspection stage."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import JobType, SourceFormat
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.pipeline.ingest.ingest import ingest_directory
from knowledge_base.pipeline.inspect.inspect import (
    detect_script_hint,
    inspect_file,
)


def _make_pdf(dirpath: Path, *, text_pages: list[str], blank_pages: int) -> Path:
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


def _ingested_source(db: Session, data_dir: Path, source_file: Path) -> SourceFile:
    ingest_directory(source_file.parent, session=db, data_dir=data_dir)
    db.commit()
    source = db.scalar(select(SourceFile))
    assert source is not None
    return source


def test_detect_script_hint() -> None:
    assert detect_script_hint("بِسْمِ اللهِ الرَّحْمَنِ الرَّحِيمِ") == "ar"
    assert detect_script_hint("بھی یہ ہے ڈ اور گ") == "ur"
    assert detect_script_hint("plain english text") == "en"
    assert detect_script_hint("1234567890") is None
    assert detect_script_hint("") is None


def test_inspect_classifies_text_pdf(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Plain English paragraph."], blank_pages=0)
    source = _ingested_source(db, data_dir, pdf)

    result = inspect_file(
        source, session=db, report_dir=data_dir / "processed" / "inspect", data_dir=data_dir
    )

    assert result.error is None
    assert result.page_count == 1
    assert result.pages_with_text == 1
    assert result.ocr_likely is False
    assert result.language_hint == "en"
    assert result.report_path is not None and result.report_path.is_file()


def test_inspect_flags_scanned_pdf(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["One text page"], blank_pages=2)
    source = _ingested_source(db, data_dir, pdf)

    result = inspect_file(
        source, session=db, report_dir=data_dir / "processed" / "inspect", data_dir=data_dir
    )

    assert result.page_count == 3
    assert result.pages_with_text == 1
    assert result.ocr_likely is True
    assert result.language_hint == "en"


def test_inspect_writes_report_and_job(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Hello world"], blank_pages=0)
    source = _ingested_source(db, data_dir, pdf)
    report_dir = data_dir / "processed" / "inspect"

    result = inspect_file(source, session=db, report_dir=report_dir, data_dir=data_dir)
    db.commit()

    report = result.report_path
    assert report is not None
    data = report.read_text(encoding="utf-8")
    assert '"language"' in data
    assert result.language_hint == "en"

    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.INSPECT))
    assert job is not None
    assert job.status == "succeeded"
    assert job.manifest["page_count"] == 1
    assert job.manifest["language_hint"] == "en"


def test_inspect_repeat_is_idempotent(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Repeat"], blank_pages=0)
    source = _ingested_source(db, data_dir, pdf)
    report_dir = data_dir / "processed" / "inspect"

    inspect_file(source, session=db, report_dir=report_dir, data_dir=data_dir)
    db.commit()
    inspect_file(source, session=db, report_dir=report_dir, data_dir=data_dir)
    db.commit()

    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.job_type == JobType.INSPECT)).all()
    assert len(jobs) == 1


def test_inspect_missing_file_is_error(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    source = SourceFile(
        sha256="9" * 64,
        file_path="does-not-exist.pdf",
        format=SourceFormat.PDF,
    )
    db.add(source)
    db.commit()

    result = inspect_file(source, session=db, report_dir=tmp_path / "processed", data_dir=data_dir)

    assert result.error is not None
    assert "cannot open pdf" in result.error
    db.commit()
    job = db.scalar(select(ProcessingJob))
    assert job is not None and job.status == "failed"


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