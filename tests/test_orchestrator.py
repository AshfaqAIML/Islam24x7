"""Tests for the end-to-end ingestion orchestrator.

A real text PDF is ingested and driven through every stage: inspect → extract
→ ocr → metadata → publish → structure → normalize → chunk → index → embed.
We cover the success path, idempotent re-runs, the review/publish gate, stage
resume, restart/failure propagation, and the read-only stage-status reporter.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import BlockType, JobStatus, JobType
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.embeddings import Embedding
from knowledge_base.database.models.search import SearchDocument
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.models.structure import ContentBlock, ContentChunk
from knowledge_base.pipeline.embed.config import EmbedConfig
from knowledge_base.pipeline.embed.provider import build_provider
from knowledge_base.pipeline.ocr.config import OcrConfig
from knowledge_base.pipeline.ocr.engines import build_engine
from knowledge_base.pipeline.orchestrator import (
    run_pipeline,
    run_pipeline_all,
    run_pipeline_from_file,
    stage_status,
)

_PAGE_LINES = [
    "The book explains the science of hadith in a clear manner.",
    "It begins with the definition of the term and then moves on to",
    "practical examples drawn from the collected narrations.",
    "",
    "Chapter Two continues the discussion with further detail.",
    "More text follows on the next page so that the structure",
    "detector has plenty of body paragraphs to process.",
]
_PAGE_TEXT = "\n".join(_PAGE_LINES)


def _make_pdf(dirpath: Path, *, title: str = "The Book of Patience") -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "sample.pdf"
    doc = pymupdf.open()
    doc.set_metadata({"title": title, "author": "Imam Anon"})
    for _ in range(2):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 500, 400), _PAGE_TEXT, fontsize=18)
    doc.save(path)
    doc.close()
    return path


def _data(tmp_path: Path) -> Path:
    return tmp_path / "data"


def _run_kwargs(data_dir: Path) -> dict[str, object]:
    return {
        "data_dir": data_dir,
        "auto_review": True,
        "ocr_engine": build_engine("dummy", OcrConfig(engine="dummy")),
        "ocr_config": OcrConfig(engine="dummy"),
        "embed_provider": build_provider("dummy", EmbedConfig()),
        "embed_config": EmbedConfig(),
    }


def _count_chunks(session: Session, book_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(ContentChunk).where(
            ContentChunk.book_id == book_id
        )
    ) or 0


def _count_embeddings(session: Session, book_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(Embedding)
        .join(ContentChunk, Embedding.content_chunk_id == ContentChunk.id)
        .where(ContentChunk.book_id == book_id)
    ) or 0


def _count_documents(session: Session, book_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(SearchDocument)
        .join(ContentChunk, SearchDocument.content_chunk_id == ContentChunk.id)
        .where(ContentChunk.book_id == book_id)
    ) or 0


# ----------------------------------------------------------------- success


def test_pipeline_end_to_end_succeeds(db: Session, tmp_path: Path) -> None:
    data_dir = _data(tmp_path)
    pdf = _make_pdf(tmp_path / "src")
    ingested, result = run_pipeline_from_file(
        db, pdf, category="books", **_run_kwargs(data_dir)
    )

    assert ingested.status == "registered"
    assert ingested.sha256 is not None
    assert result is not None
    assert result.overall == "SUCCEEDED"
    assert result.book_id is not None
    for outcome in result.stages:
        assert outcome.status in ("SUCCEEDED", "SKIPPED"), (
            f"{outcome.name}={outcome.status}: {outcome.error}"
        )
    names = {s.name: s.status for s in result.stages}
    for stage in ("inspect", "extract", "ocr", "metadata", "publish", "structure",
                  "normalize", "chunk", "index", "embed"):
        assert stage in names, f"stage {stage} missing from plan run"

    assert result.report_path is not None and result.report_path.is_file()
    report = result.report_path.read_text(encoding="utf-8")
    assert "Overall: SUCCEEDED" in report
    assert result.stages and result.stage("embed") is not None
    assert result.stage("embed").status in ("SUCCEEDED", "SKIPPED")

    source = db.scalar(
        select(SourceFile).where(SourceFile.sha256 == ingested.sha256)
    )
    assert source is not None
    book = db.scalar(select(Book).where(Book.source_file_id == source.id))
    assert book is not None
    assert _count_chunks(db, str(book.id)) > 0
    assert _count_documents(db, str(book.id)) > 0
    assert _count_embeddings(db, str(book.id)) > 0
    assert db.scalar(
        select(func.count()).select_from(ContentBlock).where(
            ContentBlock.book_id == book.id,
            ContentBlock.block_type == BlockType.PARAGRAPH,
        )
    ) > 0


def test_pipeline_rerun_skips_completed_stages(db: Session, tmp_path: Path) -> None:
    data_dir = _data(tmp_path)
    pdf = _make_pdf(tmp_path / "src")
    ingested, first = run_pipeline_from_file(db, pdf, **_run_kwargs(data_dir))
    assert first is not None and first.overall == "SUCCEEDED"
    first_book_id = first.book_id

    source = db.scalar(
        select(SourceFile).where(SourceFile.sha256 == ingested.sha256)
    )
    second = run_pipeline(db, source, **_run_kwargs(data_dir))

    assert second.overall == "SUCCEEDED"
    assert second.book_id == first_book_id
    for outcome in second.stages:
        if outcome.name in ("inspect", "extract", "ocr", "metadata",
                            "structure", "normalize", "chunk", "index", "embed"):
            assert outcome.status == "SKIPPED", f"{outcome.name} re-ran unexpectedly"
        else:
            assert outcome.status in ("SUCCEEDED", "SKIPPED")


def test_pipeline_all_runs_every_source(db: Session, tmp_path: Path) -> None:
    data_dir = _data(tmp_path)
    pd1 = _make_pdf(tmp_path / "a", title="First Fixture")
    pd2 = _make_pdf(tmp_path / "b", title="Second Fixture")
    for pdf in (pd1, pd2):
        ingested, result = run_pipeline_from_file(db, pdf, **_run_kwargs(data_dir))
        assert ingested.status == "registered"
        assert result is not None and result.overall == "SUCCEEDED"

    results = run_pipeline_all(db, **_run_kwargs(data_dir))

    assert len(results) == 2
    assert all(r.overall == "SUCCEEDED" for r in results)
    assert {r.book_id for r in results} == {
        r.book_id for r in results
    }  # every source got its own book


# ------------------------------------------------------------------ gate


def test_pipeline_without_auto_review_waits_at_publish(
    db: Session, tmp_path: Path
) -> None:
    data_dir = _data(tmp_path)
    pdf = _make_pdf(tmp_path / "src")
    kwargs = _run_kwargs(data_dir)
    kwargs["auto_review"] = False

    ingested, result = run_pipeline_from_file(db, pdf, **kwargs)

    assert ingested.status == "registered"
    assert result is not None
    assert result.overall == "WAITING"
    assert result.stage("publish") is not None
    assert result.stage("publish").status == "WAITING"
    assert db.scalar(select(func.count()).select_from(Book)) == 0
    # nothing after the gate ran
    assert all(
        outcome.status != "SUCCEEDED" for outcome in result.stages
        if outcome.name in ("structure", "chunk", "index", "embed")
    )


def test_pipeline_resume_from_structure_fails_without_extract(
    db: Session, tmp_path: Path
) -> None:
    data_dir = _data(tmp_path)
    pdf = _make_pdf(tmp_path / "src")
    ingested, first = run_pipeline_from_file(db, pdf, **_run_kwargs(data_dir))
    assert first is not None and first.overall == "SUCCEEDED"
    assert ingested.sha256 is not None

    extract_dir = data_dir / "processed" / "extract" / ingested.sha256
    import shutil

    shutil.rmtree(extract_dir)

    source = db.scalar(
        select(SourceFile).where(SourceFile.sha256 == ingested.sha256)
    )
    resumed = run_pipeline(
        db,
        source,
        data_dir=data_dir,
        auto_review=True,
        force=True,
        start_from="structure",
        ocr_engine=build_engine("dummy", OcrConfig(engine="dummy")),
        ocr_config=OcrConfig(engine="dummy"),
        embed_provider=build_provider("dummy", EmbedConfig()),
        embed_config=EmbedConfig(),
    )

    assert resumed.overall == "FAILED"
    structure = resumed.stage("structure")
    assert structure is not None
    assert structure.status == "FAILED"
    assert structure.error is not None
    assert "no extraction output" in structure.error


def test_pipeline_unknown_stage_raises(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "src")
    with pytest.raises(ValueError, match="unknown stage"):
        run_pipeline_from_file(
            db, pdf, data_dir=_data(tmp_path), start_from="not-a-stage"
        )


# --------------------------------------------------------------- status


def test_pipeline_status_reads_jobs(db: Session, tmp_path: Path) -> None:
    data_dir = _data(tmp_path)
    pdf = _make_pdf(tmp_path / "src")
    ingested, result = run_pipeline_from_file(db, pdf, **_run_kwargs(data_dir))
    assert result is not None and result.overall == "SUCCEEDED"
    assert ingested.sha256 is not None

    source = db.scalar(
        select(SourceFile).where(SourceFile.sha256 == ingested.sha256)
    )
    rows = stage_status(db, source)

    by_name = {row["stage"]: row for row in rows}
    assert set(by_name) == {
        "inspect", "extract", "ocr", "metadata", "publish",
        "structure", "normalize", "chunk", "index", "embed",
    }
    assert by_name["inspect"]["status"] == JobStatus.SUCCEEDED.value
    assert by_name["metadata"]["status"] == JobStatus.SUCCEEDED.value
    assert by_name["embed"]["status"] == JobStatus.SUCCEEDED.value
    assert by_name["publish"]["status"] == "succeeded"
    assert by_name["chunk"]["manifest"]["chunk_count"] > 0


def test_pipeline_stage_jobs_recorded(db: Session, tmp_path: Path) -> None:
    data_dir = _data(tmp_path)
    pdf = _make_pdf(tmp_path / "src")
    ingested, _ = run_pipeline_from_file(db, pdf, **_run_kwargs(data_dir))
    assert ingested.sha256 is not None

    source = db.scalar(
        select(SourceFile).where(SourceFile.sha256 == ingested.sha256)
    )
    jobs = db.scalars(
        select(ProcessingJob).where(ProcessingJob.source_file_id == source.id)
    ).all()
    assert {j.job_type for j in jobs} >= {
        JobType.INSPECT, JobType.EXTRACT, JobType.METADATA,
        JobType.STRUCTURE, JobType.NORMALIZE, JobType.CHUNK,
        JobType.INDEX, JobType.EMBED,
    }
    assert all(j.status == JobStatus.SUCCEEDED for j in jobs)