"""Tests for the ingestion pipeline stage."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import JobType, SourceStatus
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.pipeline.ingest.ingest import ingest_directory, raw_target

_PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _write(dirpath: Path, name: str, data: bytes = _PDF_BYTES) -> Path:
    path = dirpath / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_ingest_registers_and_stores(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source, "bukhari_vol_1.pdf")
    data_dir = tmp_path / "data"

    results = ingest_directory(source, session=db, data_dir=data_dir, category="hadith")
    db.commit()

    assert len(results) == 1
    assert results[0].status == "registered"
    assert results[0].target is not None
    assert results[0].target.is_file()
    assert results[0].target.read_bytes() == _PDF_BYTES
    assert results[0].target.parent.parent.parent.parent == data_dir / "raw" / "hadith"

    sf = db.scalar(select(SourceFile))
    assert sf is not None
    assert sf.status == SourceStatus.REGISTERED
    assert sf.sha256 == results[0].sha256
    assert sf.format == "pdf"
    assert sf.title_hint == "bukhari_vol_1"
    assert str(sf.file_path).startswith("raw/hadith/")

    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.INGEST))
    assert job is not None
    assert job.status == "succeeded"
    assert job.manifest["category"] == "hadith"
    assert job.manifest["size_bytes"] == len(_PDF_BYTES)


def test_ingest_duplicate_is_skipped(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source, "bukhari_vol_1.pdf")
    data_dir = tmp_path / "data"

    first = ingest_directory(source, session=db, data_dir=data_dir)
    db.commit()
    second = ingest_directory(source, session=db, data_dir=data_dir)

    assert first[0].status == "registered"
    assert second[0].status == "duplicate"
    assert len(list((data_dir / "raw").rglob("*.pdf"))) == 1


def test_ingest_duplicate_reports_existing_path(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source, "same.pdf")
    data_dir = tmp_path / "data"

    ingest_directory(source, session=db, data_dir=data_dir)
    db.commit()
    second = ingest_directory(source, session=db, data_dir=data_dir)

    assert second[0].status == "duplicate"
    assert "raw/" in (second[0].reason or "")


def test_ingest_unsupported_quarantines(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    file = _write(source, "note.exe", data=b"MZ....")
    data_dir = tmp_path / "data"

    results = ingest_directory(source, session=db, data_dir=data_dir)

    assert results[0].status == "quarantined"
    assert results[0].reason == "unsupported extension '.exe'"
    assert not file.exists()
    assert (data_dir / "quarantine" / file.name).is_file()


def test_ingest_empty_file_quarantines(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source, "blank.pdf", data=b"")
    data_dir = tmp_path / "data"

    results = ingest_directory(source, session=db, data_dir=data_dir)

    assert results[0].status == "quarantined"
    assert results[0].reason == "empty file"
    assert (data_dir / "quarantine" / "blank.pdf").is_file()


def test_ingest_recursive_nested_source(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source, "a.pdf", data=_PDF_BYTES)
    _write(source / "vol2", "b.pdf", data=b"%PDF-1.5\n%%% b copy\n")
    data_dir = tmp_path / "data"

    results = ingest_directory(source, session=db, data_dir=data_dir)

    assert {r.status for r in results} == {"registered"}
    assert sum(r.path.name.endswith(".pdf") for r in results) == 2
    assert len(list((data_dir / "raw").rglob("*.pdf"))) == 2


def test_ingest_dry_run_writes_nothing(db: Session, tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write(source, "a.pdf")
    data_dir = tmp_path / "data"

    results = ingest_directory(source, session=db, data_dir=data_dir, dry_run=True)

    assert results[0].status == "registered"
    assert not (data_dir / "raw").exists()
    assert db.scalar(select(SourceFile)) is None


@pytest.mark.parametrize(
    "name,expected",
    [
        ("x.pdf", "raw/cat/12/34/123456/x.pdf"),
        ("y.txt", "raw/cat/12/34/123456/y.txt"),
    ],
)
def test_raw_target_layout(tmp_path: Path, name: str, expected: str) -> None:
    target = raw_target(tmp_path, "cat", "123456", name)
    relative = target.relative_to(tmp_path).as_posix()
    assert relative == expected