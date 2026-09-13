"""Tests for the OCR pipeline stage (uses the deterministic dummy engine)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import JobType, OcrStatus
from knowledge_base.database.models.ocr import OcrPage
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.pipeline.extract.extract import extract_file
from knowledge_base.pipeline.ingest.ingest import ingest_directory
from knowledge_base.pipeline.ocr.config import OcrConfig
from knowledge_base.pipeline.ocr.engines import DummyEngine, build_engine
from knowledge_base.pipeline.ocr.processor import (
    assess_quality,
    density_chars,
    ocr_file,
    plan_ocr_pages,
)


def _make_text_pdf(dirpath: Path, *, text_pages: list[str]) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "book.pdf"
    doc = pymupdf.open()
    for text in text_pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=24)
    doc.save(path)
    doc.close()
    return path


def _make_scanned_pdf(dirpath: Path, *, pages: int) -> Path:
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


def _ingest(db: Session, data_dir: Path, pdf: Path) -> SourceFile:
    ingest_directory(pdf.parent, session=db, data_dir=data_dir)
    db.commit()
    source = db.scalar(select(SourceFile))
    assert source is not None
    return source


def test_assess_quality() -> None:
    config = OcrConfig()
    from knowledge_base.pipeline.ocr.engines import OcrSnippet

    ok, notes = assess_quality(
        OcrSnippet(
            "The scholars transmitted the hadith with care across many generations",
            95.0,
            ("ar",),
        ),
        config,
    )
    assert ok == OcrStatus.OK and notes == []

    status, notes = assess_quality(
        OcrSnippet("", 95.0, ("ar",)), config
    )
    assert status == OcrStatus.REVIEW
    assert "no_text" in notes

    status, _ = assess_quality(
        OcrSnippet("this is a reasonably long sentence", 10.0, ("ar",)), config
    )
    assert status == OcrStatus.REVIEW

    status, notes = assess_quality(
        OcrSnippet("????? ~~~~ ~~~!!!!", None, ("ar",)), config
    )
    assert status == OcrStatus.REVIEW
    assert any("low_alpha" in n for n in notes)


def test_plan_ocr_pages_fallback_all(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_scanned_pdf(tmp_path / "src", pages=4)
    source = _ingest(db, data_dir, pdf)

    required, total = plan_ocr_pages(source, data_dir)

    assert required == [1, 2, 3, 4]
    assert total == 4


def test_plan_ocr_pages_uses_inspect(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_text_pdf(tmp_path / "src", text_pages=["some text"] * 3)
    source = _ingest(db, data_dir, pdf)
    report_dir = data_dir / "processed" / "inspect"
    # Write an inspect report marking pages 2 and 3 as scanned.
    import json

    report_dir.mkdir(parents=True, exist_ok=True)
    detail = []
    for page in range(1, 4):
        detail.append(
            {
                "page": page,
                "chars": 100 if page == 1 else 0,
                "scanned": page != 1,
            }
        )
    (report_dir / f"{source.sha256}.json").write_text(
        json.dumps({"pdf": {"page_count": 3}, "pages": {"detail": detail}}),
        encoding="utf-8",
    )

    required, total = plan_ocr_pages(source, data_dir)

    assert required == [2, 3]
    assert total == 3


def test_ocr_scanned_pdf_renders_and_records_all_pages(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_scanned_pdf(tmp_path / "src", pages=3)
    source = _ingest(db, data_dir, pdf)
    engine = DummyEngine()
    out_root = data_dir / "processed" / "ocr" / source.sha256

    result = ocr_file(
        source,
        session=db,
        engine=engine,
        config=OcrConfig(engine="dummy"),
        data_dir=data_dir,
    )
    db.commit()

    assert result.error is None
    assert result.pages_required == 3
    assert result.pages_ocr == 3
    assert result.pages_skipped == 0
    assert result.engine == "dummy"
    assert result.engine_version == "0.1.0"
    assert (out_root / "render" / "0001.png").is_file()
    assert (out_root / "render" / "0002.png").is_file()
    assert (out_root / "render" / "0003.png").is_file()
    assert (out_root / "text" / "0001.txt").is_file()
    assert (out_root / "text" / "0002.txt").is_file()
    assert (out_root / "text" / "0003.txt").is_file()
    assert (out_root / "report.json").is_file()
    assert (out_root / "report.txt").is_file()

    rows = db.scalars(select(OcrPage).order_by(OcrPage.page_number)).all()
    assert len(rows) == 3
    for row in rows:
        assert row.engine == "dummy"
        assert row.engine_version == "0.1.0"
        assert row.status == OcrStatus.OK
        assert row.confidence == 95.0
        assert row.text_path
        assert row.image_path
        assert row.text_path != row.image_path  # text stored separately

    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.OCR))
    assert job is not None
    assert job.status == "succeeded"
    assert job.manifest["engine"] == "dummy"
    assert job.manifest["pages_ocr"] == 3


def test_ocr_marks_low_confidence_for_review(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_scanned_pdf(tmp_path / "src", pages=2)
    source = _ingest(db, data_dir, pdf)
    engine = DummyEngine(
        defaults=("solid page text for the engine output", 12.0),
        by_page={2: ("", 0.0)},
    )

    result = ocr_file(
        source,
        session=db,
        engine=engine,
        config=OcrConfig(engine="dummy", min_confidence=50.0),
        data_dir=data_dir,
    )
    db.commit()

    assert result.pages_review == 2
    rows = {r.page_number: r for r in db.scalars(select(OcrPage))}
    assert rows[1].status == OcrStatus.REVIEW
    assert rows[1].quality_notes == "low_confidence=12.0"
    assert rows[2].status == OcrStatus.REVIEW
    assert "no_text" in rows[2].quality_notes  # empty text → review, never guessed


def test_ocr_mixed_book_only_scanned_pages(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    scan_dir = tmp_path / "scan"
    scanned = _make_scanned_pdf(scan_dir, pages=2)
    text_dir = tmp_path / "src"
    text_pdf = _make_text_pdf(
        text_dir,
        text_pages=["A real text page with enough words to count as text."],
    )
    merged_dir = tmp_path / "mixed"
    merged_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    scan_src = pymupdf.open(str(scanned))
    doc.insert_pdf(scan_src)
    text_src = pymupdf.open(str(text_pdf))
    doc.insert_pdf(text_src)
    scan_src.close()
    text_src.close()
    merged = merged_dir / "mixed.pdf"
    doc.save(merged)
    doc.close()

    source = _ingest(db, data_dir, merged)
    # Run extraction first so the plan knows page 1 is clean text.
    extract_file(
        source,
        session=db,
        output_dir=data_dir / "processed" / "extract" / source.sha256,
        data_dir=data_dir,
    )
    db.commit()

    # The merged document is: pages 1-2 scanned, page 3 clean text.
    required, total = plan_ocr_pages(source, data_dir)
    assert required == [1, 2]
    assert total == 3

    engine = DummyEngine()
    result = ocr_file(
        source,
        session=db,
        engine=engine,
        config=OcrConfig(engine="dummy"),
        data_dir=data_dir,
    )
    db.commit()
    assert result.pages_ocr == 2
    rows = db.scalars(select(OcrPage)).all()
    assert sorted(r.page_number for r in rows) == [1, 2]


def test_ocr_idempotent_skips_existing_pages(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_scanned_pdf(tmp_path / "src", pages=2)
    source = _ingest(db, data_dir, pdf)
    engine = DummyEngine()
    config = OcrConfig(engine="dummy")

    first = ocr_file(source, session=db, engine=engine, config=config, data_dir=data_dir)
    db.commit()
    second = ocr_file(source, session=db, engine=engine, config=config, data_dir=data_dir)
    db.commit()

    assert first.pages_ocr == 2
    assert second.pages_skipped == 2
    assert second.pages_ocr == 0
    assert db.scalars(select(OcrPage)).all()  # rows exist
    assert len(db.scalars(select(OcrPage)).all()) == 2
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.OCR))
    assert job is not None and job.manifest["pages_skipped"] == 2


def test_ocr_force_reruns(db: Session, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    pdf = _make_scanned_pdf(tmp_path / "src", pages=1)
    source = _ingest(db, data_dir, pdf)
    engine = DummyEngine()
    config = OcrConfig(engine="dummy")

    ocr_file(source, session=db, engine=engine, config=config, data_dir=data_dir)
    db.commit()
    result = ocr_file(
        source, session=db, engine=engine, config=config, data_dir=data_dir, force=True
    )
    db.commit()

    assert result.pages_ocr == 1
    assert len(db.scalars(select(OcrPage)).all()) == 1
    assert db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.OCR)).manifest[
        "pages_ocr"
    ] == 1


def test_build_engine_dummy_and_unknown() -> None:
    assert isinstance(build_engine("dummy", OcrConfig()), DummyEngine)
    from knowledge_base.pipeline.ocr.engines import OcrEngineUnavailable

    try:
        build_engine("definitely-not-real", OcrConfig())
    except OcrEngineUnavailable:
        pass
    else:
        pytest.fail("expected OcrEngineUnavailable")


def test_density_chars() -> None:
    assert density_chars("ab c d") == 4
    assert density_chars("") == 0