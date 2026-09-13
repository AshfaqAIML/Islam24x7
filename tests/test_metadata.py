"""Tests for the book metadata extraction & review pipeline."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import (
    JobType,
    MetadataConfidence,
    MetadataField,
    MetadataReviewStatus,
    MetadataSource,
)
from knowledge_base.database.models.books import Book, Category
from knowledge_base.database.models.metadata import MetadataCandidate
from knowledge_base.database.models.sources import ProcessingJob, SourceEdition, SourceFile
from knowledge_base.pipeline.ingest.ingest import ingest_directory
from knowledge_base.pipeline.metadata.config import DEFAULT_METADATA_CONFIG
from knowledge_base.pipeline.metadata.extractors import (
    extract_from_filename,
    extract_from_pages,
    extract_from_pdf_metadata,
)
from knowledge_base.pipeline.metadata.processor import (
    apply_review,
    extract_metadata,
    merge_candidates,
    overall_confidence,
    publish_metadata,
)

AR_TITLE = "فقه الحنفي"
AR_AUTHOR = "علامة فلان الخير آبادي"


def _make_pdf(
    dirpath: Path,
    filename: str,
    *,
    meta: dict[str, str] | None = None,
    pages: list[str] | None = None,
) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / filename
    doc = pymupdf.open()
    if meta:
        doc.set_metadata(meta)  # type: ignore[no-untyped-call]
    for text in pages or [""]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=20)  # type: ignore[no-untyped-call]
    doc.save(path)
    doc.close()
    return path


def _ingest(db: Session, data_dir: Path, pdf: Path) -> SourceFile:
    ingest_directory(pdf.parent, session=db, data_dir=data_dir)
    db.commit()
    source = db.scalar(select(SourceFile))
    assert source is not None
    return source


# ---------------------------------------------------------------- extractors


def test_pdf_metadata_extractor() -> None:
    results = extract_from_pdf_metadata(
        {"title": "Example Fiqh Book", "author": "Example Author", "subject": "A study of fiqh"}
    )
    by_field = {(r.field, r.source): r for r in results}
    title_row = by_field[(MetadataField.TITLE, MetadataSource.PDF_METADATA)]
    author_row = by_field[(MetadataField.AUTHOR, MetadataSource.PDF_METADATA)]
    assert title_row.value == "Example Fiqh Book"
    assert title_row.confidence == MetadataConfidence.HIGH
    assert not title_row.uncertain
    assert author_row.value == "Example Author"
    desc = by_field[(MetadataField.DESCRIPTION, MetadataSource.PDF_METADATA)]
    assert desc.confidence == MetadataConfidence.MEDIUM

    assert extract_from_pdf_metadata({}) == []


def test_filename_title_guess_is_uncertain() -> None:
    hits = extract_from_filename("Example-Fiqh-Book.pdf", DEFAULT_METADATA_CONFIG)
    title = [r for r in hits if r.field == MetadataField.TITLE]
    assert len(title) == 1
    assert title[0].value == "Example Fiqh Book"
    assert title[0].confidence == MetadataConfidence.LOW
    assert title[0].uncertain
    assert title[0].source == MetadataSource.FILENAME


def test_filename_generic_and_volume() -> None:
    assert extract_from_filename("book.pdf", DEFAULT_METADATA_CONFIG) == []
    assert extract_from_filename("README.md", DEFAULT_METADATA_CONFIG) == []

    hits = extract_from_filename("jamiy_tirmidhi_vol_2.pdf", DEFAULT_METADATA_CONFIG)
    editions = [r for r in hits if r.field == MetadataField.EDITION]
    titles = [r for r in hits if r.field == MetadataField.TITLE]
    assert editions and editions[0].value == "Vol. 2"
    assert not editions[0].uncertain
    assert titles and titles[0].value == "jamiy tirmidhi"


def test_title_page_markers() -> None:
    page_text = (
        "بسم الله الرحمن الرحيم\n"
        f"{AR_TITLE}\n"
        f"تأليف: {AR_AUTHOR}\n"
        "تحقيق: شخص آخر\n"
        "الطبعة الثانية\n"
        "۱۳۹۲هـ"
    )
    hits = extract_from_pages([(1, page_text)], DEFAULT_METADATA_CONFIG)
    by_field: dict[MetadataField, list] = {}
    for hit in hits:
        by_field.setdefault(hit.field, []).append(hit)

    author = by_field[MetadataField.AUTHOR][0]
    assert author.value == AR_AUTHOR
    assert author.confidence == MetadataConfidence.HIGH
    assert not author.uncertain
    assert author.source == MetadataSource.TITLE_PAGE

    editor = by_field[MetadataField.EDITOR][0]
    assert editor.value == "شخص آخر"

    edition = by_field[MetadataField.EDITION][0]
    assert edition.value == "الطبعة الثانية"

    year = by_field[MetadataField.PUBLICATION_YEAR][0]
    assert year.value == "1392 (AH)"
    assert year.confidence == MetadataConfidence.HIGH
    assert not year.uncertain

    title = by_field[MetadataField.TITLE][0]
    assert title.value == AR_TITLE
    assert title.confidence == MetadataConfidence.MEDIUM
    assert title.uncertain

    lang = by_field[MetadataField.LANGUAGE][0]
    assert lang.value == "ar"


def test_bare_four_digit_is_uncertain() -> None:
    hits = extract_from_pages([(1, "1420")], DEFAULT_METADATA_CONFIG)
    years = [r for r in hits if r.field == MetadataField.PUBLICATION_YEAR]
    assert len(years) == 1
    assert years[0].value == "1420"
    assert years[0].confidence == MetadataConfidence.MEDIUM
    assert years[0].uncertain


def test_isbn_detection() -> None:
    hits = extract_from_pages(
        [(2, "المعرف الرقمي: ISBN 978-969-1234-56-7")], DEFAULT_METADATA_CONFIG
    )
    isbns = [r for r in hits if r.field == MetadataField.ISBN]
    assert len(isbns) == 1
    assert isbns[0].value == "9789691234567"
    assert isbns[0].confidence == MetadataConfidence.HIGH


def test_no_invention_on_blank_or_trivial_pages() -> None:
    assert extract_from_pages([(1, ""), (2, "")], DEFAULT_METADATA_CONFIG) == []
    assert extract_from_pages([(1, "1\n2\n3")], DEFAULT_METADATA_CONFIG) == []


# ------------------------------------------------------------ merge / report


def _row(
    db: Session,
    source: SourceFile,
    field: MetadataField,
    value: str,
    *,
    confidence: MetadataConfidence = MetadataConfidence.MEDIUM,
    source_: MetadataSource = MetadataSource.FIRST_PAGES,
    uncertain: bool = True,
    status: MetadataReviewStatus = MetadataReviewStatus.PENDING,
) -> MetadataCandidate:
    row = MetadataCandidate(
        source_file_id=source.id,
        field=field,
        value=value,
        confidence=confidence,
        uncertain=uncertain,
        source=source_,
        status=status,
    )
    db.add(row)
    return row


def test_merge_ranks_by_status_then_confidence(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "a.pdf", pages=["hello world"])
    source = _ingest(db, tmp_path, pdf)
    low = _row(db, source, MetadataField.TITLE, "Slug Guess", confidence=MetadataConfidence.LOW)
    high = _row(db, source, MetadataField.TITLE, "Real Title", confidence=MetadataConfidence.HIGH)
    db.flush()

    best = merge_candidates(db.scalars(select(MetadataCandidate)).all(), DEFAULT_METADATA_CONFIG)
    assert best[MetadataField.TITLE] is high  # high confidence wins

    low.status = MetadataReviewStatus.APPROVED
    db.flush()
    best = merge_candidates(db.scalars(select(MetadataCandidate)).all(), DEFAULT_METADATA_CONFIG)
    assert best[MetadataField.TITLE] is low  # explicit approval overrides confidence

    rejected_page = _row(
        db, source, MetadataField.TITLE, "Rejected", confidence=MetadataConfidence.HIGH,
        status=MetadataReviewStatus.REJECTED,
    )
    db.flush()
    best = merge_candidates(db.scalars(select(MetadataCandidate)).all(), DEFAULT_METADATA_CONFIG)
    assert rejected_page not in best.values()


def test_overall_confidence_is_weakest_link(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "b.pdf", pages=["x"])
    source = _ingest(db, tmp_path, pdf)
    _row(db, source, MetadataField.TITLE, "T", confidence=MetadataConfidence.HIGH)
    _row(db, source, MetadataField.LANGUAGE, "ar", confidence=MetadataConfidence.MEDIUM)
    db.flush()
    best = merge_candidates(db.scalars(select(MetadataCandidate)).all(), DEFAULT_METADATA_CONFIG)
    assert overall_confidence(best) == "medium"


# ------------------------------------------------------------- processor flow


def test_extract_metadata_persists_idempotently(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path,
        "Example-Fiqh-Book.pdf",
        meta={"title": "Example Fiqh Book", "author": AR_AUTHOR},
        pages=["by Example Author", "1420"],
    )
    source = _ingest(db, tmp_path, pdf)

    result = extract_metadata(source, session=db, data_dir=tmp_path)
    db.commit()
    assert result.error is None
    assert result.summary_path is not None and result.summary_path.is_file()
    assert result.report_path is not None and result.report_path.is_file()
    rows = db.scalars(select(MetadataCandidate)).all()
    assert len(rows) >= 5  # pdf title/author + filename title + title_page + language + page_count
    fields = {r.field for r in rows}
    assert MetadataField.TITLE in fields and MetadataField.AUTHOR in fields

    job = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.source_file_id == source.id,
            ProcessingJob.job_type == JobType.METADATA,
        )
    )
    assert job is not None and job.status.value == "succeeded"
    assert job.manifest["fields"] and "uncertain_fields" in job.manifest

    extract_metadata(source, session=db, data_dir=tmp_path)
    db.commit()
    rows2 = db.scalars(select(MetadataCandidate)).all()
    assert len(rows2) == len(rows)  # idempotent: no duplicate candidates


def test_user_provided_wins_and_is_approved(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "Slug-Filename.pdf", pages=["some text"])
    source = _ingest(db, tmp_path, pdf)
    extract_metadata(
        source,
        session=db,
        data_dir=tmp_path,
        user_items=[("title", "The Real Title"), ("category", "Fiqh")],
    )
    db.commit()
    rows = db.scalars(select(MetadataCandidate)).all()
    titles = [r for r in rows if r.field == MetadataField.TITLE]
    approved_user = [r for r in titles if r.source == MetadataSource.USER_PROVIDED]
    slug = [r for r in titles if r.source == MetadataSource.FILENAME]
    assert len(approved_user) == 1
    assert approved_user[0].status == MetadataReviewStatus.APPROVED
    assert slug  # the guess is still recorded but user input wins the merge

    best = merge_candidates(rows, DEFAULT_METADATA_CONFIG)
    assert best[MetadataField.TITLE].value == "The Real Title"

    cat = db.scalar(
        select(MetadataCandidate).where(MetadataCandidate.field == MetadataField.CATEGORY)
    )
    assert cat is not None and cat.value == "Fiqh"


def test_uncertain_metadata_is_never_published_without_approval(
    db: Session, tmp_path: Path
) -> None:
    pdf = _make_pdf(tmp_path, "Example-Fiqh-Book.pdf", pages=["text"])
    source = _ingest(db, tmp_path, pdf)
    extract_metadata(source, session=db, data_dir=tmp_path)
    db.commit()

    result = publish_metadata(db, source)
    assert result.errors  # no approved title yet
    assert db.scalar(select(Book)) is None
    assert db.scalar(select(SourceEdition)) is None


def test_review_approve_and_publish(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path,
        "Example-Fiqh-Book.pdf",
        meta={"title": "Example Fiqh Book", "author": AR_AUTHOR},
        pages=["by Example Author"],
    )
    source = _ingest(db, tmp_path, pdf)
    extract_metadata(source, session=db, data_dir=tmp_path)
    db.commit()

    target, error = apply_review(db, source, "title", approve=True, reviewer="tester")
    assert error is None and target is not None
    apply_review(db, source, "author", approve=True, reviewer="tester")
    apply_review(db, source, "language", approve=True, reviewer="tester")
    _ = _row(
        db, source, MetadataField.CATEGORY, "Fiqh", confidence=MetadataConfidence.HIGH,
        source_=MetadataSource.USER_PROVIDED, uncertain=False,
        status=MetadataReviewStatus.APPROVED,
    )
    db.commit()

    result = publish_metadata(db, source, reviewer="tester")
    db.commit()
    assert not result.errors, result.errors
    assert result.book_id and result.edition_id

    book = db.scalar(select(Book))
    assert book is not None
    assert book.title == "Example Fiqh Book"
    assert book.author is not None and book.author.name == AR_AUTHOR
    assert book.category is not None and book.category.name == "Fiqh"
    assert book.language == "en"
    assert book.edition_id is not None

    edition = db.scalar(select(SourceEdition))
    assert edition is not None and edition.title == "Example Fiqh Book"

    assert db.scalar(select(Category)) is not None


def test_reject_keeps_candidate_out_of_publish(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path,
        "Example-Fiqh-Book.pdf",
        meta={"title": "Example Fiqh Book", "author": "Wrong Author Name"},
        pages=[],
    )
    source = _ingest(db, tmp_path, pdf)
    extract_metadata(source, session=db, data_dir=tmp_path)
    db.commit()

    apply_review(db, source, "author", reject=True, reviewer="tester")
    apply_review(db, source, "title", approve=True, reviewer="tester")
    db.commit()
    result = publish_metadata(db, source)
    db.commit()
    assert not result.errors
    book = db.scalar(select(Book))
    assert book is not None and book.author is None  # rejected author not published


def test_review_corrects_value_via_cli(db: Session, tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path, "Needs-Correction.pdf", pages=["some text"])
    source = _ingest(db, tmp_path, pdf)
    extract_metadata(source, session=db, data_dir=tmp_path)
    db.commit()

    target, error = apply_review(
        db, source, "title", approve=True, value="Corrected Title", reviewer="tester"
    )
    assert error is None and target is not None
    db.commit()
    best = merge_candidates(
        db.scalars(select(MetadataCandidate)).all(), DEFAULT_METADATA_CONFIG
    )
    assert best[MetadataField.TITLE].value == "Corrected Title"
    assert best[MetadataField.TITLE].status == MetadataReviewStatus.APPROVED
    assert best[MetadataField.TITLE].source == MetadataSource.USER_PROVIDED