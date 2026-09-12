"""Tests for the text extraction stage."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import JobType, SourceFormat
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.pipeline.extract.extract import extract_file
from knowledge_base.pipeline.ingest.ingest import ingest_directory


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


def _ingested(db: Session, data_dir: Path, pdf: Path) -> SourceFile:
    ingest_directory(pdf.parent, session=db, data_dir=data_dir)
    db.commit()
    source = db.scalar(select(SourceFile))
    assert source is not None
    return source


def test_extract_writes_page_files(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["First page text", "Second page text"])
    source = _ingested(db, data_dir, pdf)
    output_dir = data_dir / "processed" / "extract" / source.sha256

    result = extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)

    assert result.error is None
    assert result.page_count == 2
    assert result.pages_with_text == 2
    assert result.chars_total > 0
    assert (output_dir / "pages").is_dir()
    for name in ("0001.txt", "0002.txt"):
        assert (output_dir / "pages" / name).is_file()
    assert (output_dir / "index.json").is_file()


def test_extract_records_job(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Hello extraction"])
    source = _ingested(db, data_dir, pdf)
    output_dir = data_dir / "processed" / "extract" / source.sha256

    extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)
    db.commit()

    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.EXTRACT))
    assert job is not None
    assert job.status == "succeeded"
    assert job.manifest["page_count"] == 1
    assert job.manifest["pages_with_text"] == 1


def test_extract_blank_pages_skip_files(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Text on page one"], blank_pages=2)
    source = _ingested(db, data_dir, pdf)
    output_dir = data_dir / "processed" / "extract" / source.sha256

    result = extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)

    assert result.page_count == 3
    assert result.pages_with_text == 1
    assert result.pages[1].file_name is None
    assert (output_dir / "pages" / "0001.txt").is_file()
    assert not (output_dir / "pages" / "0002.txt").exists()


def test_extract_garbled_pages_skip_files_and_flag(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    # Clean Latin text, then pages whose glyphs don't map to real letters
    # (the classic Arabic/Urdu PDF symptom: mostly '?' or punctuation).
    pdf = _make_pdf(
        tmp_path / "src",
        text_pages=["Clean readable English", "????? ?????", '""\'P ~II!1J\\S'],
    )
    source = _ingested(db, data_dir, pdf)
    output_dir = data_dir / "processed" / "extract" / source.sha256

    result = extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)

    assert result.page_count == 3
    assert result.pages_ok == 1
    assert result.pages_garbled == 2
    assert result.pages_with_text == 3
    assert (output_dir / "pages" / "0001.txt").is_file()
    assert not (output_dir / "pages" / "0002.txt").exists()
    assert not (output_dir / "pages" / "0003.txt").exists()
    index = (output_dir / "index.json").read_text(encoding="utf-8")
    assert '"quality": "garbled"' in index


def test_extract_idempotent_job_single_record(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_pdf(tmp_path / "src", text_pages=["Repeat me"])
    source = _ingested(db, data_dir, pdf)
    output_dir = data_dir / "processed" / "extract" / source.sha256

    extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)
    db.commit()
    extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)
    db.commit()

    jobs = db.scalars(select(ProcessingJob).where(ProcessingJob.job_type == JobType.EXTRACT)).all()
    assert len(jobs) == 1


def test_extract_missing_file_reports_failed(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    source = SourceFile(
        sha256="7" * 64,
        file_path="does-not-exist.pdf",
        format=SourceFormat.PDF,
    )
    db.add(source)
    db.commit()

    result = extract_file(
        source, session=db, output_dir=tmp_path / "processed", data_dir=data_dir
    )
    db.commit()

    assert result.error is not None
    index = (tmp_path / "processed" / "index.json").read_text(encoding="utf-8")
    assert '"error"' in index
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.EXTRACT))
    assert job is not None and job.status == "failed"


def test_extract_preserves_text_order(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    first = "First line of the first paragraph."
    second = "Second line continues the paragraph."
    pdf = _make_pdf(tmp_path / "src", text_pages=[f"{first}\n{second}"])
    source = _ingested(db, data_dir, pdf)
    output_dir = data_dir / "processed" / "extract" / source.sha256

    result = extract_file(source, session=db, output_dir=output_dir, data_dir=data_dir)

    text = (output_dir / "pages" / "0001.txt").read_text(encoding="utf-8")
    assert first in text and second in text
    assert result.pages_with_text == 1