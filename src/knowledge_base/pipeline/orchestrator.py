"""End-to-end book ingestion orchestrator.

Runs the source and book stages in sequence for one registered source file
(and optionally from a raw file), recording per-stage outcomes, a pipeline
report, and a verdict:

    inspect -> extract -> ocr -> metadata -> [review+gate] -> structure
    -> normalize -> chunk -> index -> embed

Each stage is idempotent and restartable: stages already recorded as
``SUCCEEDED`` are skipped unless ``force`` is set, and the run may be resumed
from any point with ``start_from``/``stop_at``. The publish gate between
metadata and structure needs either an already-published ``Book`` or
``auto_review`` (which approves high-confidence candidates and materializes
the book). OCR only runs on pages marked for OCR by the extract artifacts, so
text PDFs need no engine; the embedding stage needs a provider, otherwise it
is skipped and reported.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import (
    ContentStatus,
    JobStatus,
    JobType,
    MetadataConfidence,
    MetadataField,
    MetadataReviewStatus,
)
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.metadata import MetadataCandidate
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.models.structure import ContentBlock

# ------------------------------------------------------------------- model

PLAN: tuple[tuple[str, JobType | None, str], ...] = (
    ("inspect", JobType.INSPECT, "source"),
    ("extract", JobType.EXTRACT, "source"),
    ("ocr", JobType.OCR, "source"),
    ("metadata", JobType.METADATA, "source"),
    ("publish", None, "gate"),
    ("structure", JobType.STRUCTURE, "book"),
    ("normalize", JobType.NORMALIZE, "book"),
    ("chunk", JobType.CHUNK, "book"),
    ("index", JobType.INDEX, "book"),
    ("embed", JobType.EMBED, "book"),
)

STAGE_NAMES: list[str] = [name for name, _job, _level in PLAN]

_MANIFEST_INTERESTING = (
    "page_count",
    "pages_with_text",
    "pages_ocr",
    "chunk_count",
    "document_count",
    "embedded_count",
    "updated_count",
    "reused_count",
    "model_name",
    "model_version",
)


@dataclass
class StageOutcome:
    """Outcome of one pipeline stage for a source file."""

    name: str
    status: str  # SUCCEEDED | SKIPPED | FAILED | WAITING
    detail: str = ""
    count: int | None = None
    error: str | None = None
    elapsed_ms: int = 0


@dataclass
class PipelineResult:
    """Per-source pipeline run: stage outcomes, verdict, and report path."""

    sha256: str
    source_file_id: str
    book_id: str | None = None
    overall: str = "SUCCEEDED"  # SUCCEEDED | WAITING | FAILED
    stages: list[StageOutcome] = field(default_factory=list)
    report_path: Path | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None

    def stage(self, name: str) -> StageOutcome | None:
        for outcome in self.stages:
            if outcome.name == name:
                return outcome
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "source_file_id": self.source_file_id,
            "book_id": self.book_id,
            "overall": self.overall,
            "stages": [
                {
                    "stage": s.name,
                    "status": s.status,
                    "detail": s.detail,
                    "count": s.count,
                    "error": s.error,
                    "elapsed_ms": s.elapsed_ms,
                }
                for s in self.stages
            ],
            "report_path": str(self.report_path) if self.report_path else None,
        }

    def report_lines(self) -> list[str]:
        lines = [f"Pipeline for {self.sha256[:12]} (source {self.source_file_id[:8]})"]
        if self.book_id:
            lines.append(f"Book: {self.book_id[:12]}")
        lines.append(f"Overall: {self.overall}")
        lines.append("")
        for s in self.stages:
            count = f"  [{s.count}]" if s.count is not None else ""
            hit = f"  ERROR: {s.error}" if s.error else ""
            lines.append(f"{s.status:9s} {s.name}{count}  {s.detail}{hit}")
        lines.append("")
        return lines


# --------------------------------------------------------------- internals


@dataclass(frozen=True)
class _Context:
    data_dir: Path
    force: bool
    auto_review: bool
    continue_on_error: bool
    reviewer: str
    ocr_engine: Any | None
    ocr_config: Any
    embed_provider: Any | None
    embed_config: Any


def _default_data_dir() -> Path:
    from knowledge_base.config import get_settings

    return get_settings().resolve().data_dir


def _find_book(session: Session, source: SourceFile) -> Book | None:
    return session.scalar(select(Book).where(Book.source_file_id == source.id))


def _stage_job(session: Session, source_id: Any, job_type: JobType) -> ProcessingJob | None:
    return session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source_id,
            ProcessingJob.job_type == job_type,
        )
    )


def _job_done(session: Session, source_id: Any, job_type: JobType) -> bool:
    job = _stage_job(session, source_id, job_type)
    if job is None:
        return False
    current = job.status if isinstance(job.status, str) else job.status.value
    return current == JobStatus.SUCCEEDED.value


def _job_summary(job: ProcessingJob | None) -> str:
    if job is None:
        return ""
    parts = [f"{key}={job.manifest[key]}" for key in _MANIFEST_INTERESTING if key in job.manifest]
    tail = f" ({', '.join(parts)})" if parts else ""
    return tail


def _report_path(data_dir: Path, sha256: str) -> Path:
    return data_dir / "processed" / "pipeline" / f"{sha256}.txt"


def _write_report(result: PipelineResult) -> None:
    if result.report_path is None:
        return
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    result.report_path.write_text("\n".join(result.report_lines()), encoding="utf-8")


def _select_plan(
    start_from: str | None, stop_at: str | None
) -> list[tuple[str, JobType | None, str]]:
    names = [name for name, _job, _level in PLAN]
    if start_from:
        if start_from not in names:
            raise ValueError(f"unknown stage {start_from!r}; choose from {', '.join(names)}")
        names = names[names.index(start_from) :]
    if stop_at:
        if stop_at not in names:
            raise ValueError(f"unknown stage {stop_at!r}; choose from {', '.join(names)}")
        names = names[: names.index(stop_at) + 1]
    return [entry for entry in PLAN if entry[0] in names]


# ---------------------------------------------------------------- dispatch


def _run_inspect(session: Session, source: SourceFile, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.inspect.inspect import inspect_file

    result = inspect_file(
        source,
        session=session,
        report_dir=ctx.data_dir / "processed" / "inspect",
        data_dir=ctx.data_dir,
    )
    classification = getattr(result, "classification", None)
    label = classification.value if classification else f"pages={result.page_count}"
    return StageOutcome(
        "inspect",
        "FAILED" if result.error else "SUCCEEDED",
        detail=label,
        count=result.page_count,
        error=result.error,
    )


def _run_extract(session: Session, source: SourceFile, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.extract.extract import extract_file

    result = extract_file(
        source,
        session=session,
        output_dir=ctx.data_dir / "processed" / "extract" / source.sha256,
        data_dir=ctx.data_dir,
    )
    return StageOutcome(
        "extract",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"pages={result.page_count} with_text={result.pages_with_text}",
        count=result.page_count,
        error=result.error,
    )


def _run_ocr(session: Session, source: SourceFile, ctx: _Context) -> StageOutcome:
    if ctx.ocr_engine is None:
        return StageOutcome(
            "ocr", "SKIPPED", detail="ocr engine not available (text PDFs need none)"
        )
    from knowledge_base.pipeline.ocr.processor import ocr_file

    result = ocr_file(
        source,
        session=session,
        engine=ctx.ocr_engine,
        config=ctx.ocr_config,
        data_dir=ctx.data_dir,
        force=ctx.force,
    )
    return StageOutcome(
        "ocr",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"required={result.pages_required} ocr={result.pages_ocr} "
        f"review={result.pages_review}",
        count=result.pages_required,
        error=result.error,
    )


def _run_metadata(session: Session, source: SourceFile, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.metadata.processor import extract_metadata

    result = extract_metadata(source, session=session, config=None, data_dir=ctx.data_dir)
    guess = result.best_guess or {}
    best_title = guess.get("title")
    title = best_title.get("value") if isinstance(best_title, dict) else (best_title or "—")
    return StageOutcome(
        "metadata",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"candidates={len(guess)} title={title}",
        count=len(guess),
        error=result.error,
    )


def _run_publish_gate(session: Session, source: SourceFile, ctx: _Context) -> StageOutcome:
    book = _find_book(session, source)
    if book is not None:
        return StageOutcome("publish", "SUCCEEDED", detail=f"book already published {book.id}")
    if not ctx.auto_review:
        return StageOutcome(
            "publish",
            "WAITING",
            detail="metadata review + publish required (run with --auto-review "
            "or approve candidates and re-run)",
        )
    errors = _auto_review_and_publish(session, source, ctx.reviewer)
    if errors:
        return StageOutcome("publish", "FAILED", detail="; ".join(errors))
    book = _find_book(session, source)
    session.flush()
    return StageOutcome(
        "publish",
        "SUCCEEDED",
        detail=f"book created {book.id}" if book else "no book row",
    )


def _auto_review_and_publish(session: Session, source: SourceFile, reviewer: str) -> list[str]:
    from knowledge_base.pipeline.metadata.config import DEFAULT_METADATA_CONFIG
    from knowledge_base.pipeline.metadata.processor import (
        apply_review,
        merge_candidates,
        publish_metadata,
    )

    rows = session.scalars(
        select(MetadataCandidate).where(MetadataCandidate.source_file_id == source.id)
    ).all()
    best = merge_candidates(list(rows), DEFAULT_METADATA_CONFIG)
    errors: list[str] = []
    for meta_field, candidate in best.items():
        if candidate.status not in (
            MetadataReviewStatus.PENDING,
            MetadataReviewStatus.REVIEW,
        ):
            continue
        if meta_field == MetadataField.TITLE and candidate.confidence != MetadataConfidence.HIGH:
            errors.append(f"title confidence is {candidate.confidence.value}; approve manually")
            continue
        if candidate.confidence == MetadataConfidence.HIGH:
            apply_review(session, source, meta_field.value, approve=True, reviewer=reviewer)
    if errors:
        return errors
    session.flush()
    publish = publish_metadata(session, source, reviewer=reviewer)
    session.flush()
    return list(publish.errors)


def _run_structure(session: Session, book: Book, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.structure.processor import detect_structure

    result = detect_structure(book, session=session, data_dir=ctx.data_dir)
    blocks = session.scalars(
        select(ContentBlock).where(
            ContentBlock.book_id == book.id,
            ContentBlock.status == ContentStatus.REVIEW,
        )
    ).all()
    reviewed = 0
    if blocks and ctx.auto_review:
        for block in blocks:
            block.status = ContentStatus.PUBLISHED
            reviewed += 1
    note = f" review-blocks={reviewed}" if reviewed else ""
    return StageOutcome(
        "structure",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"pages={result.page_count}{note}",
        count=result.page_count,
        error=result.error,
    )


def _run_normalize(session: Session, book: Book, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.normalize.processor import normalize_book

    result = normalize_book(book, session=session, data_dir=ctx.data_dir, config_name="auto")
    return StageOutcome(
        "normalize",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"blocks={result.blocks_total} normalized={result.blocks_normalized}",
        count=result.blocks_total,
        error=result.error,
    )


def _run_chunk(session: Session, book: Book, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.chunk.processor import chunk_book

    result = chunk_book(book, session=session, data_dir=ctx.data_dir)
    return StageOutcome(
        "chunk",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"chunks={result.chunk_count} tokens={result.token_total}",
        count=result.chunk_count,
        error=result.error,
    )


def _run_index(session: Session, book: Book, ctx: _Context) -> StageOutcome:
    from knowledge_base.pipeline.index.index import index_book

    result = index_book(book, session=session, data_dir=ctx.data_dir)
    return StageOutcome(
        "index",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"documents={result.document_count}",
        count=result.document_count,
        error=result.error,
    )


def _run_embed(session: Session, book: Book, ctx: _Context) -> StageOutcome:
    if ctx.embed_provider is None:
        return StageOutcome("embed", "SKIPPED", detail="embedding provider not available")
    from knowledge_base.pipeline.embed.processor import embed_book

    result = embed_book(
        book,
        session=session,
        data_dir=ctx.data_dir,
        provider=ctx.embed_provider,
        config=ctx.embed_config,
    )
    return StageOutcome(
        "embed",
        "FAILED" if result.error else "SUCCEEDED",
        detail=f"embedded={result.embedded_count} updated={result.updated_count} "
        f"reused={result.reused_count}",
        count=result.chunk_count,
        error=result.error,
    )


# ------------------------------------------------------------------ public

_SOURCE_DISPATCH: dict[str, Any] = {
    "inspect": _run_inspect,
    "extract": _run_extract,
    "ocr": _run_ocr,
    "metadata": _run_metadata,
}

_BOOK_DISPATCH: dict[str, Any] = {
    "structure": _run_structure,
    "normalize": _run_normalize,
    "chunk": _run_chunk,
    "index": _run_index,
    "embed": _run_embed,
}


def _execute_source_stage(
    session: Session, name: str, source: SourceFile, ctx: _Context
) -> StageOutcome:
    fn = _SOURCE_DISPATCH[name]
    return cast(StageOutcome, fn(session, source, ctx))


def _execute_book_stage(session: Session, name: str, book: Book, ctx: _Context) -> StageOutcome:
    fn = _BOOK_DISPATCH[name]
    return cast(StageOutcome, fn(session, book, ctx))


def run_pipeline(
    session: Session,
    source: SourceFile,
    *,
    data_dir: Path | None = None,
    force: bool = False,
    auto_review: bool = False,
    continue_on_error: bool = False,
    start_from: str | None = None,
    stop_at: str | None = None,
    reviewer: str = "pipeline",
    ocr_engine: Any | None = None,
    ocr_config: Any | None = None,
    embed_provider: Any | None = None,
    embed_config: Any | None = None,
) -> PipelineResult:
    """Run the plan for one already-registered source file."""
    from knowledge_base.pipeline.embed.config import EmbedConfig
    from knowledge_base.pipeline.ocr.config import OcrConfig

    if data_dir is None:
        data_dir = _default_data_dir()
    ctx = _Context(
        data_dir=data_dir,
        force=force,
        auto_review=auto_review,
        continue_on_error=continue_on_error,
        reviewer=reviewer,
        ocr_engine=ocr_engine,
        ocr_config=ocr_config or OcrConfig(),
        embed_provider=embed_provider,
        embed_config=embed_config or EmbedConfig(),
    )
    plan = _select_plan(start_from, stop_at)
    result = PipelineResult(
        sha256=source.sha256,
        source_file_id=str(source.id),
        report_path=_report_path(data_dir, source.sha256),
    )
    book = _find_book(session, source)
    if book is not None:
        result.book_id = str(book.id)

    for name, job_type, level in plan:
        if level == "gate":
            started = time.perf_counter()
            outcome = _run_publish_gate(session, source, ctx)
            outcome.elapsed_ms = int((time.perf_counter() - started) * 1000)
            if outcome.status == "SUCCEEDED":
                book = _find_book(session, source)
                if book is not None:
                    result.book_id = str(book.id)
            result.stages.append(outcome)
            if outcome.status == "WAITING":
                result.overall = "WAITING"
                break
            if outcome.status == "FAILED":
                result.overall = "FAILED"
                if not ctx.continue_on_error:
                    break
            continue

        if level == "book" and book is None:
            result.stages.append(StageOutcome(name, "WAITING", detail="no published book"))
            result.overall = "WAITING"
            break

        if job_type is not None and not force and _job_done(session, source.id, job_type):
            job = _stage_job(session, source.id, job_type)
            result.stages.append(
                StageOutcome(name, "SKIPPED", detail=f"already completed{_job_summary(job)}")
            )
            continue

        started = time.perf_counter()
        if level == "book":
            assert book is not None
            outcome = _execute_book_stage(session, name, book, ctx)
        else:
            outcome = _execute_source_stage(session, name, source, ctx)
        outcome.elapsed_ms = int((time.perf_counter() - started) * 1000)
        session.flush()
        result.stages.append(outcome)
        if outcome.status == "FAILED":
            result.overall = "FAILED"
            if not ctx.continue_on_error:
                break
        elif outcome.status == "WAITING":
            result.overall = "WAITING"
            break

    if all(s.status in ("SUCCEEDED", "SKIPPED") for s in result.stages):
        result.overall = "SUCCEEDED"
    _write_report(result)
    session.flush()
    result.finished_at = datetime.now()
    return result


def run_pipeline_from_file(
    session: Session,
    path: Path,
    *,
    category: str = "books",
    data_dir: Path | None = None,
    **run_kwargs: Any,
) -> tuple[Any, PipelineResult | None]:
    """Ingest a raw file, then run the plan on the resulting source.

    Returns ``(ingestion_result, pipeline_result)``; ``pipeline_result`` is
    ``None`` when the file was quarantined or failed to ingest. A duplicate
    file resumes the existing source's pipeline (restartable).
    """
    from knowledge_base.pipeline.ingest.ingest import ingest_file

    data_dir = data_dir or _default_data_dir()
    ingested = ingest_file(path, session=session, data_dir=data_dir, category=category)
    if ingested.status not in ("registered", "duplicate"):
        return ingested, None
    source = session.scalar(select(SourceFile).where(SourceFile.sha256 == ingested.sha256))
    if source is None:
        return ingested, None
    return ingested, run_pipeline(session, source, data_dir=data_dir, **run_kwargs)


def run_pipeline_all(
    session: Session,
    *,
    data_dir: Path | None = None,
    limit: int | None = None,
    **run_kwargs: Any,
) -> list[PipelineResult]:
    """Run the plan over every registered source in creation order."""
    sources = session.scalars(select(SourceFile).order_by(SourceFile.created_at)).all()
    results: list[PipelineResult] = []
    for source in sources[:limit] if limit is not None else sources:
        results.append(run_pipeline(session, source, data_dir=data_dir, **run_kwargs))
    return results


def stage_status(session: Session, source: SourceFile) -> list[dict[str, object]]:
    """Read-only per-stage job status for one source (for ``pipeline status``)."""
    book = _find_book(session, source)
    rows: list[dict[str, object]] = []
    for name, job_type, level in PLAN:
        entry: dict[str, object] = {"stage": name, "level": level}
        if level == "gate":
            entry["status"] = "succeeded" if book is not None else "waiting"
            entry["detail"] = f"book {book.id}" if book is not None else "review + publish required"
            rows.append(entry)
            continue
        job = _stage_job(session, source.id, job_type) if job_type is not None else None
        job_status = job.status if job is not None else None
        entry["status"] = (
            "not_run"
            if job_status is None
            else (job_status.value if isinstance(job_status, JobStatus) else str(job_status))
        )
        entry["detail"] = _job_summary(job)
        entry["manifest"] = job.manifest if job is not None else {}
        entry["error"] = job.error if job is not None else None
        rows.append(entry)
    return rows


__all__ = [
    "PLAN",
    "STAGE_NAMES",
    "PipelineResult",
    "StageOutcome",
    "run_pipeline",
    "run_pipeline_all",
    "run_pipeline_from_file",
    "stage_status",
]
