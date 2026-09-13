"""Metadata processor: orchestrate extraction, review, and publication.

Pipeline flow for one source file::

    extract candidates (pdf info / filename / first pages / user input)
        └─ persist into metadata_candidates (review state preserved across runs)
    merge candidates into a best-guess per field
        └─ write report.json / report.txt (confidence + uncertainty per field)
    human review: approve / correct / reject fields
        └─ publish approved fields into source_editions + books

Nothing extracted automatically is ever moved into the verified catalog:
publication requires an explicit ``approve`` + ``publish`` step.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import (
    JobStatus,
    JobType,
    MetadataConfidence,
    MetadataField,
    MetadataReviewStatus,
    MetadataSource,
)
from knowledge_base.database.models.books import Author, Book, Category, Publisher, Translator
from knowledge_base.database.models.metadata import MetadataCandidate
from knowledge_base.database.models.sources import SourceEdition, SourceFile
from knowledge_base.logging import logger
from knowledge_base.pipeline.jobs import upsert_processing_job
from knowledge_base.pipeline.metadata.config import DEFAULT_METADATA_CONFIG, MetadataConfig
from knowledge_base.pipeline.metadata.extractors import (
    CandidateExtract,
    extract_from_filename,
    extract_from_pages,
    extract_from_pdf_metadata,
    extract_from_user,
)

_CONF_RANK = {
    MetadataConfidence.HIGH: 0,
    MetadataConfidence.MEDIUM: 1,
    MetadataConfidence.LOW: 2,
}
_FIELD_ORDER = [
    MetadataField.TITLE,
    MetadataField.SUBTITLE,
    MetadataField.AUTHOR,
    MetadataField.TRANSLATOR,
    MetadataField.EDITOR,
    MetadataField.PUBLISHER,
    MetadataField.PUBLICATION_YEAR,
    MetadataField.EDITION,
    MetadataField.LANGUAGE,
    MetadataField.ISBN,
    MetadataField.CATEGORY,
    MetadataField.DESCRIPTION,
    MetadataField.PAGE_COUNT,
]


@dataclass
class MetadataResult:
    """Outcome of extracting/reporting metadata for one source file."""

    sha256: str
    source_file_id: str
    file_name: str
    fields_found: list[str] = field(default_factory=list)
    review_needed: list[str] = field(default_factory=list)
    overall_confidence: str | None = None
    best_guess: dict[str, dict[str, object]] = field(default_factory=dict)
    candidates: list[dict[str, object]] = field(default_factory=list)
    report_path: Path | None = None
    summary_path: Path | None = None
    error: str | None = None


@dataclass
class PublishResult:
    """Outcome of materializing approved metadata into the catalog."""

    book_id: str | None = None
    edition_id: str | None = None
    created_book: bool = False
    created_edition: bool = False
    fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def merge_candidates(
    candidates: list[MetadataCandidate], config: MetadataConfig
) -> dict[MetadataField, MetadataCandidate]:
    """Best candidate per field, honoring approvals/rejections + confidence."""
    by_field: dict[MetadataField, list[MetadataCandidate]] = {}
    for candidate in candidates:
        by_field.setdefault(candidate.field, []).append(candidate)

    best: dict[MetadataField, MetadataCandidate] = {}
    for field_, rows in by_field.items():
        live = [r for r in rows if r.status != MetadataReviewStatus.REJECTED]
        if not live:
            continue
        approved = [r for r in live if r.status == MetadataReviewStatus.APPROVED]
        ordered = sorted(
            approved or live,
            key=lambda r: (
                _CONF_RANK[r.confidence],
                -config.source_priority.get(r.source.value, 0),
            ),
        )
        best[field_] = ordered[0]
    return best


def overall_confidence(best: dict[MetadataField, MetadataCandidate]) -> str | None:
    """Label the overall confidence as the weakest link among found fields."""
    if not best:
        return None
    worst = max(_CONF_RANK[candidate.confidence] for candidate in best.values())
    return [c.value for c in MetadataConfidence][worst]


def _report_dir(data_dir: Path) -> Path:
    return data_dir.resolve() / "processed" / "metadata"


def _field_label(field: MetadataField) -> str:
    return field.value.replace("_", " ").capitalize()


def render_report_text(
    file_name: str,
    best: dict[MetadataField, MetadataCandidate],
    overall: str | None,
    missing: list[MetadataField],
    error: str | None,
) -> str:
    lines = [file_name]
    for field_ in _FIELD_ORDER:
        candidate = best.get(field_)
        if candidate is None:
            lines.append(f"{_field_label(field_)}: (not found)")
            continue
        mark = "  [uncertain]" if candidate.uncertain else ""
        lines.append(f"{_field_label(field_)}: {candidate.value}{mark}")
    lines.append(f"Metadata confidence: {overall or 'none'}")
    if missing:
        lines.append(f"Missing fields: {', '.join(_field_label(f) for f in missing)}")
    if best:
        lines.append("")
        lines.append("Per-field candidates:")
        for field_ in _FIELD_ORDER:
            candidates = [c for c in best.values() if c.field == field_]
            for candidate in candidates:
                meta = (
                    f"conf={candidate.confidence.value} src={candidate.source.value} "
                    f"status={candidate.status.value}"
                    + (" uncertain" if candidate.uncertain else "")
                )
                evidence = f"  evidence: {candidate.evidence}" if candidate.evidence else ""
                lines.append(f"  {_field_label(field_)}: {candidate.value}  [{meta}]{evidence}")
    if error:
        lines.append(f"Error: {error}")
    return "\n".join(lines) + "\n"


def extract_metadata(
    source_file: SourceFile,
    *,
    session: Session,
    config: MetadataConfig | None = None,
    data_dir: Path,
    user_items: list[tuple[str, str]] | None = None,
) -> MetadataResult:
    """Extract + persist metadata candidates and write the merge report."""
    config = config or DEFAULT_METADATA_CONFIG
    result = MetadataResult(
        sha256=source_file.sha256,
        source_file_id=str(source_file.id),
        file_name=Path(source_file.file_path).name,
    )
    root = data_dir.resolve()
    path = root / source_file.file_path
    report_dir = _report_dir(root)
    result.best_guess = {}  # replaced below

    extracts: list[CandidateExtract] = []
    pdf_meta: dict[str, str] = {}
    page_texts: list[tuple[int, str]] = []

    if source_file.format.value == "pdf":
        try:
            document = pymupdf.open(str(path))  # type: ignore[no-untyped-call]
        except Exception as exc:
            result.error = f"cannot open pdf: {exc}"
            _finish(result, session, report_dir, config)
            return result
        with document:
            if not document.needs_pass:
                pdf_meta = {k: str(v) for k, v in (document.metadata or {}).items() if v}
                if source_file.size_bytes is not None:
                    pass  # page count handled below
                render_limit = min(config.scan_first_pages, document.page_count)
                for index in range(render_limit):
                    page_texts.append(
                        (index + 1, document.load_page(index).get_text("text"))  # type: ignore[no-untyped-call]
                    )
                extracts.extend(extract_from_pdf_metadata(pdf_meta))
                extracts.extend(extract_from_pages(page_texts, config))
            else:
                result.error = "pdf is encrypted"
                _finish(result, session, report_dir, config)
                return result
    if config.use_filename:
        extracts.extend(extract_from_filename(path.name, config))
    if user_items:
        extracts.extend(extract_from_user(user_items))
    page_count = _count_pages(source_file, root, page_texts)
    if page_count is not None:
        extracts.append(
            CandidateExtract(
                MetadataField.PAGE_COUNT,
                str(page_count),
                MetadataConfidence.HIGH,
                False,
                MetadataSource.PDF_METADATA,
                "page count from the pdf",
            )
        )

    _persist(session, source_file.id, extracts)
    session.flush()
    candidates = session.scalars(
        select(MetadataCandidate)
        .where(MetadataCandidate.source_file_id == source_file.id)
        .order_by(MetadataCandidate.created_at)
    ).all()
    best = merge_candidates(list(candidates), config)

    found_fields = sorted(best.keys(), key=lambda f: _FIELD_ORDER.index(f))
    result.fields_found = [f.value for f in found_fields]
    result.review_needed = [
        candidate.field.value
        for candidate in best.values()
        if candidate.uncertain or candidate.confidence != MetadataConfidence.HIGH
    ]
    result.overall_confidence = overall_confidence(best)
    result.best_guess = {
        c.field.value: c.as_dict() for c in (best[f] for f in found_fields)
    }
    result.candidates = [c.as_dict() for c in candidates]

    missing = [f for f in _FIELD_ORDER if f not in best]
    _write_reports(result, best, missing, report_dir)
    _upsert_job(session, result)
    return result


def _count_pages(
    source_file: SourceFile, root: Path, page_texts: list[tuple[int, str]]
) -> int | None:
    """Page count for a PDF, reusing the inspection report when present."""
    if source_file.format.value != "pdf":
        return None
    inspect_report = root / "processed" / "inspect" / f"{source_file.sha256}.json"
    try:
        if inspect_report.is_file():
            data = json.loads(inspect_report.read_text(encoding="utf-8"))
            count = int(data.get("pdf", {}).get("page_count", 0))
            if count:
                return count
    except Exception:
        pass
    if page_texts:
        return max(page_no for page_no, _ in page_texts)
    return None


def _persist(
    session: Session, source_file_id: uuid.UUID, extracts: list[CandidateExtract]
) -> None:
    existing = session.scalars(
        select(MetadataCandidate).where(MetadataCandidate.source_file_id == source_file_id)
    ).all()
    by_key = {
        (c.field, c.source, c.value): c
        for c in existing
    }
    new_keys: set[tuple[MetadataField, MetadataSource, str]] = set()
    for extract in extracts:
        key = (extract.field, extract.source, extract.value)
        new_keys.add(key)
        row = by_key.get(key)
        if row is not None:
            row.confidence = extract.confidence
            if row.source == MetadataSource.USER_PROVIDED:
                row.uncertain = extract.uncertain or row.uncertain
            else:
                row.uncertain = row.uncertain or extract.uncertain
            if not row.evidence and extract.evidence:
                row.evidence = extract.evidence
            continue
        row = MetadataCandidate(
            source_file_id=source_file_id,
            field=extract.field,
            value=extract.value,
            confidence=extract.confidence,
            uncertain=extract.uncertain,
            source=extract.source,
            evidence=extract.evidence,
        )
        if extract.source == MetadataSource.USER_PROVIDED:
            row.status = MetadataReviewStatus.APPROVED
            row.reviewed_at = datetime.now(UTC)
            row.reviewed_by = "operator"
        session.add(row)

    for candidate in existing:
        key = (candidate.field, candidate.source, candidate.value)
        if key not in new_keys:
            session.delete(candidate)


def _write_reports(
    result: MetadataResult,
    best: dict[MetadataField, MetadataCandidate],
    missing: list[MetadataField],
    report_dir: Path,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{result.sha256}.json"
    payload: dict[str, object] = {
        "source": {"sha256": result.sha256, "source_file_id": result.source_file_id},
        "file_name": result.file_name,
        "best_guess": result.best_guess,
        "overall_confidence": result.overall_confidence,
        "review_needed": result.review_needed,
        "candidates": result.candidates,
        "error": result.error,
        "extracted_at": datetime.now(UTC).isoformat(),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.report_path = json_path
    summary_path = report_dir / f"{result.sha256}.txt"
    summary_path.write_text(
        render_report_text(
            result.file_name, best, result.overall_confidence, missing, result.error
        ),
        encoding="utf-8",
    )
    result.summary_path = summary_path


def _upsert_job(session: Session, result: MetadataResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    confidence_counts = {level.value: 0 for level in MetadataConfidence}
    for candidate in result.candidates:
        confidence_counts[str(candidate["confidence"])] += 1
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.METADATA,
        status=status,
        manifest={
            "fields": result.fields_found,
            "candidate_count": len(result.candidates),
            "confidence_counts": confidence_counts,
            "uncertain_fields": [
                c["field"] for c in result.candidates if c["uncertain"]
            ],
            "review_needed": result.review_needed,
            "overall_confidence": result.overall_confidence,
            "report": result.report_path.name if result.report_path else None,
        },
        error=result.error,
    )


def _finish(
    result: MetadataResult, session: Session, report_dir: Path, config: MetadataConfig
) -> None:
    _write_reports(result, {}, list(_FIELD_ORDER), report_dir)
    _upsert_job(session, result)


def extract_metadata_all(
    session: Session,
    *,
    settings: Settings | None = None,
    config: MetadataConfig | None = None,
    limit: int | None = None,
    user_items: list[tuple[str, str]] | None = None,
) -> list[MetadataResult]:
    """Extract metadata for every registered source file."""
    if settings is None:
        settings = get_settings()
    config = config or DEFAULT_METADATA_CONFIG
    sources = session.scalars(select(SourceFile).order_by(SourceFile.created_at)).all()
    if limit is not None:
        sources = sources[:limit]

    results: list[MetadataResult] = []
    for source in sources:
        logger.info("metadata {}", source.sha256[:12])
        results.append(
            extract_metadata(
                source,
                session=session,
                config=config,
                data_dir=settings.data_dir,
                user_items=user_items,
            )
        )
    return results


def apply_review(
    session: Session,
    source_file: SourceFile,
    field_name: str,
    *,
    approve: bool = False,
    reject: bool = False,
    value: str | None = None,
    note: str | None = None,
    reviewer: str = "cli",
) -> tuple[MetadataCandidate | None, str | None]:
    """Approve / reject / correct the best candidate for a field."""
    from knowledge_base.pipeline.metadata.extractors import parse_field

    try:
        field = parse_field(field_name)
    except ValueError as exc:
        return None, str(exc)

    rows = session.scalars(
        select(MetadataCandidate).where(
            MetadataCandidate.source_file_id == source_file.id,
            MetadataCandidate.field == field,
        )
    ).all()
    if not rows:
        return None, f"no {field.value} candidate to review"
    target = merge_candidates(list(rows), DEFAULT_METADATA_CONFIG).get(field)
    if target is None:
        return None, f"no available {field.value} candidate (all rejected?)"

    if value is not None:
        target.value = " ".join(value.split())
        target.source = MetadataSource.USER_PROVIDED
        target.confidence = MetadataConfidence.HIGH
        target.uncertain = False
        target.evidence = (target.evidence or "") + " [corrected by reviewer]"
    if approve:
        target.status = MetadataReviewStatus.APPROVED
    elif reject:
        target.status = MetadataReviewStatus.REJECTED
    if note is not None:
        target.review_note = note
    if approve or reject or value is not None or note is not None:
        target.reviewed_at = datetime.now(UTC)
        target.reviewed_by = reviewer
    return target, None


def publish_metadata(
    session: Session,
    source_file: SourceFile,
    *,
    reviewer: str = "cli",
) -> PublishResult:
    """Materialize approved candidates into ``source_editions`` + ``books``."""
    result = PublishResult()
    rows = session.scalars(
        select(MetadataCandidate).where(
            MetadataCandidate.source_file_id == source_file.id,
            MetadataCandidate.status == MetadataReviewStatus.APPROVED,
        )
    ).all()
    approved: dict[MetadataField, MetadataCandidate] = {}
    for row in rows:
        approved.setdefault(row.field, row)

    title = approved.get(MetadataField.TITLE)
    if title is None:
        result.errors.append("no approved title — approve a title before publishing")
        return result

    result.fields = [f.value for f in approved]

    edition = session.scalar(
        select(SourceEdition).where(SourceEdition.source_file_id == source_file.id)
    )
    if edition is None:
        edition = SourceEdition(source_file_id=source_file.id, title=title.value)
        session.add(edition)
        result.created_edition = True
    else:
        edition.title = title.value
    _apply_edition_fields(edition, approved, result)

    book = session.scalar(
        select(Book).where(
            Book.source_file_id == source_file.id, Book.title == title.value
        )
    )
    if book is None:
        book = Book(source_file_id=source_file.id, title=title.value)
        session.add(book)
        result.created_book = True
    else:
        book.title = title.value
    session.flush()
    book.edition_id = edition.id
    _apply_book_fields(session, book, approved, result)
    session.flush()
    result.edition_id = str(edition.id)
    result.book_id = str(book.id)
    return result


def _apply_edition_fields(
    edition: SourceEdition,
    approved: dict[MetadataField, MetadataCandidate],
    result: PublishResult,
) -> None:
    subtitle = approved.get(MetadataField.SUBTITLE)
    if subtitle:
        edition.subtitle = subtitle.value
    language = approved.get(MetadataField.LANGUAGE)
    if language and language.value in {"ar", "ur", "en", "other"}:
        edition.language = language.value
    publisher = approved.get(MetadataField.PUBLISHER)
    if publisher:
        edition.publisher = publisher.value
    isbn = approved.get(MetadataField.ISBN)
    if isbn:
        digits = re.sub(r"[^0-9xX]", "", isbn.value)
        if digits:
            edition.isbn = digits[-13:] if len(digits) >= 13 else digits
    year = approved.get(MetadataField.PUBLICATION_YEAR)
    if year:
        _set_year(edition, year, result)


def _set_year(
    edition: SourceEdition, candidate: MetadataCandidate, result: PublishResult
) -> None:
    match = re.search(r"\d+", candidate.value)
    if match:
        edition.publication_year = int(match.group(0))
        if "(AH)" in candidate.value:
            note = edition.notes or ""
            if "publication year as printed" not in note:
                edition.notes = f"{note} publication year as printed (Hijri)".strip()
    else:
        result.errors.append(f"cannot publish publication_year {candidate.value!r}")


def _apply_book_fields(
    session: Session,
    book: Book,
    approved: dict[MetadataField, MetadataCandidate],
    result: PublishResult,
) -> None:
    subtitle = approved.get(MetadataField.SUBTITLE)
    if subtitle:
        book.subtitle = subtitle.value
    language = approved.get(MetadataField.LANGUAGE)
    if language and language.value in {"ar", "ur", "en", "other"}:
        book.language = language.value

    author = approved.get(MetadataField.AUTHOR)
    if author:
        book.author = _by_name(session, Author, author.value)
    translator = approved.get(MetadataField.TRANSLATOR)
    if translator:
        book.translator = _by_name(session, Translator, translator.value)
    publisher = approved.get(MetadataField.PUBLISHER)
    if publisher:
        book.publisher = _by_name(session, Publisher, publisher.value)
    category = approved.get(MetadataField.CATEGORY)
    if category:
        book.category = _category_by_name(session, category.value)

    editor = approved.get(MetadataField.EDITOR)
    if editor:
        edition = book.edition
        if edition is not None:
            note = edition.notes or ""
            edition.notes = f"{note} editor: {editor.value}".strip()


def _by_name(
    session: Session,
    model: type[Any],
    name: str,
) -> Any:
    """Get-or-create a catalog entity by its unique ``name``."""
    row = session.scalar(select(model).where(model.name == name))
    if row is None:
        row = model(name=name)
        session.add(row)
    return row


def _category_by_name(session: Session, name: str) -> Category:
    row = session.scalar(select(Category).where(Category.name == name))
    if row is None:
        code = _slugify(name)
        row = session.scalar(select(Category).where(Category.code == code))
        if row is not None:
            return row
        base = code if code else name
        row = Category(code=base, name=name)
        session.add(row)
    return row


def _slugify(text: str) -> str:
    """ASCII slug; falls back to a transliterated-ish lowercased key."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:64]


__all__ = [
    "MetadataResult",
    "PublishResult",
    "apply_review",
    "extract_metadata",
    "extract_metadata_all",
    "merge_candidates",
    "overall_confidence",
    "publish_metadata",
    "render_report_text",
]