"""Tests for the document structure detection pipeline.

Layered as: unit tests for heading/config helpers, then end-to-end tests that
write extract-style ``pages/*.txt`` (plus an ``index.json`` when testing blank
pages) and run the full detector against the database, including idempotency.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge_base.database.enums import (
    BlockType,
    ChapterKind,
    ContentStatus,
    JobType,
    SourceFormat,
)
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.sources import ProcessingJob, SourceFile
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    Page,
    Paragraph,
    Section,
    Subsection,
)
from knowledge_base.pipeline.structure.config import DEFAULT_STRUCTURE_CONFIG
from knowledge_base.pipeline.structure.heading import (
    detect_heading,
    normalize_arabic,
    translate_digits,
)
from knowledge_base.pipeline.structure.processor import (
    detect_structure,
    load_extract_pages,
    looks_like_toc_line,
)

CONFIG = DEFAULT_STRUCTURE_CONFIG


def _write_extract(data_dir: Path, sha256: str, pages: dict[int, str]) -> None:
    """Write extract-style output (pages only, no index) for a sha."""
    pages_dir = data_dir / "processed" / "extract" / sha256 / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for page_no, text in pages.items():
        (pages_dir / f"{page_no:04d}.txt").write_text(text, encoding="utf-8")


def _write_extract_with_index(data_dir: Path, sha256: str, pages: dict[int, str | None]) -> None:
    """Write extract output with an index declaring blank pages (None)."""
    root = data_dir / "processed" / "extract" / sha256
    pages_dir = root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    page_files = []
    for page_no, text in pages.items():
        entry = {"page": page_no, "chars": len(text or ""), "quality": "ok" if text else "blank"}
        if text:
            name = f"{page_no:04d}.txt"
            (pages_dir / name).write_text(text, encoding="utf-8")
            entry["file"] = name
        page_files.append(entry)
    index = {
        "pages": {"total": max(pages), "with_text": sum(1 for t in pages.values() if t)},
        "page_files": page_files,
    }
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")


def _make_book(session: Session, data_dir: Path, sha256: str, pages: dict[int, str]) -> Book:
    source = SourceFile(
        sha256=sha256,
        file_path=f"books/{sha256}.pdf",
        format=SourceFormat.PDF,
    )
    session.add(source)
    session.flush()
    book = Book(source_file_id=source.id, title="Fixture Book")
    session.add(book)
    session.flush()
    _write_extract(data_dir, sha256, pages)
    return book


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# -------------------------------------------------------------------- unit tests


def test_arabic_normalization_helpers() -> None:
    assert translate_digits("١٢٣") == "123"
    assert translate_digits("۱٤۵") == "145"
    assert normalize_arabic("البابُ الأول المزيد") == "الباب الاول المزيد"
    assert normalize_arabic("کتاب فقه") == "كتاب فقه"
    assert "أإآ" and normalize_arabic("أحمد إبراهيم آدم ة")  # smoke: no crash


def test_heading_markup_levels() -> None:
    chapter = detect_heading("الباب الأول في الفقه", CONFIG)
    assert chapter is not None
    assert chapter.level == 1
    assert chapter.number == 1

    section = detect_heading("الفصل الرابع – أحكام الطهارة", CONFIG)
    assert section is not None
    assert section.level == 2
    assert section.number == 4

    subsection = detect_heading("المسألة الأولى", CONFIG)
    assert subsection is not None
    assert subsection.level == 3
    assert subsection.number == 1

    appendix = detect_heading("الملحق: خرائط", CONFIG)
    assert appendix is not None
    assert appendix.level == 1
    assert appendix.kind == ChapterKind.APPENDIX

    references = detect_heading("References", CONFIG)
    assert references is not None
    assert references.level == 1
    assert references.references is True


def test_heading_partial_word_guard() -> None:
    assert detect_heading("بابا الجميل", CONFIG) is None
    assert detect_heading("فصلان من الكتاب", CONFIG) is None
    assert detect_heading("Chaptering the rest", CONFIG) is None
    assert detect_heading("Partition walls are great", CONFIG) is None


def test_dotted_numbering_levels() -> None:
    section = detect_heading("1.1 صلاة الجماعة", CONFIG)
    assert section is not None
    assert section.level == 2
    subsection = detect_heading("٢.٣.١ تفاصيل", CONFIG)
    assert subsection is not None
    assert subsection.level == 3
    single = detect_heading("12. نص وحيد", CONFIG)
    assert single is None  # single "N." is not a confident structural marker


def test_page_number_and_toc_lines() -> None:
    assert looks_like_toc_line("Chapter One .............. 7", CONFIG)
    assert looks_like_toc_line("الفصل الأول ............ ٥", CONFIG)
    assert looks_like_toc_line("A normal prose sentence for a body page.", CONFIG) is False


# ------------------------------------------------------------------ English book


EN_PAGES = {
    1: "The Example Book\nby Test Author\n1",
    2: "Contents\nIntroduction .......... 5\nChapter One .......... 7\nChapter Two ......... 12\n2",
    3: "The Introduction\n\nThis is the introduction text for the front matter.\n3",
    4: "Chapter 1\nSome opening prose of chapter one.\n4",
    5: "Chapter 1\n1.1 First Section\nParagraph in section one.\n"
    "1.1.1 A subsection\nParagraph in the subsection.\n5",
    6: "Chapter 2\nProse for chapter two.\n1.1 Second Section\nMore prose.\n6",
    7: "Text with a note.\n(1) This is a footnote.\n7",
    8: "References\nSmith, J. (2020). Some citation.\nDoe, A. A book.\n8",
}


def test_detect_english_book(db: Session, tmp_path: Path) -> None:
    book = _make_book(db, tmp_path, "aa" * 32, EN_PAGES)
    result = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()

    assert result.error is None
    assert result.page_count == 8
    assert result.pages_with_text == 8
    assert result.toc_pages == [2]
    assert result.front_matter_pages == [1, 3]
    assert result.chapters_by_kind == {
        "chapter": 3,
        "table_of_contents": 1,
        "front_matter": 1,
    }
    assert result.section_count == 2
    assert result.subsection_count == 1
    assert result.paragraph_count == 6
    assert result.flagged_count == 1
    assert result.suppressed_repeats == 1  # "Chapter 1" running header on page 5
    assert result.dropped_page_numbers == 8
    assert result.blocks_by_type["paragraph"] == 6
    assert result.blocks_by_type["toc_entry"] == 4
    assert result.blocks_by_type["footnote"] == 1
    assert result.blocks_by_type["reference"] == 1
    assert result.blocks_by_type["heading"] == 7

    chapters = db.scalars(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.number)
    ).all()
    assert len(chapters) == 5
    by_number = {c.number: c for c in chapters}
    assert by_number[-1].kind == ChapterKind.TABLE_OF_CONTENTS
    assert by_number[0].kind == ChapterKind.FRONT_MATTER
    assert by_number[1].title == "Chapter 1"
    assert by_number[2].title == "Chapter 2"
    assert by_number[3].title == "References"

    sections = db.scalars(
        select(Section).where(Section.book_id == book.id).order_by(Section.number)
    ).all()
    assert len(sections) == 2
    assert {s.title for s in sections} == {"First Section", "Second Section"}

    subsections = db.scalars(select(Subsection).where(Subsection.book_id == book.id)).all()
    assert [s.title for s in subsections] == ["A subsection"]

    pages = db.scalars(select(Page).where(Page.book_id == book.id)).all()
    assert len(pages) == 8
    assert all(p.has_text for p in pages)

    paragraphs = db.scalars(select(Paragraph).where(Paragraph.book_id == book.id)).all()
    assert len(paragraphs) == 6
    assert all(p.text.strip() for p in paragraphs)

    # paragraph inside the subsection is properly parented
    sub_block = db.scalars(
        select(ContentBlock).where(
            ContentBlock.book_id == book.id,
            ContentBlock.block_type == BlockType.PARAGRAPH,
        )
    ).all()
    detail = next(
        block for block in sub_block if "Paragraph in the subsection" in block.original_text
    )
    assert detail.subsection is not None
    assert detail.subsection.title == "A subsection"
    assert detail.chapter is not None
    assert detail.chapter.title == "Chapter 1"

    # footnote and reference blocks are present with status validated
    blocks = db.scalars(select(ContentBlock).where(ContentBlock.book_id == book.id)).all()
    footnote = next(b for b in blocks if b.block_type == BlockType.FOOTNOTE)
    assert "footnote" in footnote.original_text.lower()
    ref = next(b for b in blocks if b.block_type == BlockType.REFERENCE)
    assert "Smith" in ref.original_text
    # flagged possible heading has review status
    flagged = next(b for b in blocks if b.status == ContentStatus.REVIEW)
    assert flagged.block_type == BlockType.HEADING
    assert flagged.notes


def test_detect_english_book_idempotent(db: Session, tmp_path: Path) -> None:
    book = _make_book(db, tmp_path, "bb" * 32, EN_PAGES)
    first = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()
    db.expire_all()
    second = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()

    assert second.error is None
    assert (first.page_count, first.paragraph_count, first.block_count) == (
        second.page_count,
        second.paragraph_count,
        second.block_count,
    )
    assert first.flagged_count == second.flagged_count
    chapters = db.scalars(select(Chapter).where(Chapter.book_id == book.id)).all()
    assert len(chapters) == 5
    assert _count(db, Section) == 2
    assert _count(db, Subsection) == 1
    assert _count(db, Paragraph) == 6
    assert _count(db, ContentBlock) == first.block_count


# ------------------------------------------------------------------- Arabic book


AR_PAGES = {
    1: "بسم الله الرحمن الرحيم\nالحمد لله والصلاة والسلام على رسول الله\n١",
    2: "الباب الأول\nهذا نص الباب الأول.\n٢",
    3: "الفصل الأول\nنص في الفصل الأول.\n٣",
    4: "المسألة الأولى\nنص المسألة الأولى.\n(١) حاشية على المسألة.\n٤",
    5: "الملحق\nالمحتوى الملحق هنا.\n٥",
}


def test_detect_arabic_book(db: Session, tmp_path: Path) -> None:
    book = _make_book(db, tmp_path, "cc" * 32, AR_PAGES)
    result = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()

    assert result.error is None
    assert result.toc_pages == []
    assert result.front_matter_pages == [1]
    assert result.chapters_by_kind == {
        "chapter": 1,
        "appendix": 1,
        "front_matter": 1,
    }
    assert result.section_count == 1
    assert result.subsection_count == 1
    assert result.flagged_count == 0
    assert result.dropped_page_numbers == 5

    chapters = db.scalars(
        select(Chapter).where(Chapter.book_id == book.id).order_by(Chapter.number)
    ).all()
    assert [c.title for c in chapters] == ["(front matter)", "الباب الأول", "الملحق"]

    section = db.scalars(select(Section).where(Section.book_id == book.id)).one()
    assert section.title == "الفصل الأول"
    subsection = db.scalars(select(Subsection).where(Subsection.book_id == book.id)).one()
    assert subsection.title == "المسألة الأولى"

    blocks = db.scalars(select(ContentBlock).where(ContentBlock.book_id == book.id)).all()
    footnote = next(b for b in blocks if b.block_type == BlockType.FOOTNOTE)
    assert "حاشية" in footnote.original_text
    detail = next(
        b for b in blocks if b.block_type == BlockType.PARAGRAPH and "المسألة" in b.original_text
    )
    assert detail.subsection is not None
    assert detail.subsection.title == "المسألة الأولى"


# ------------------------------------------------------------- non-standard book


def test_detect_plain_book_no_fabricated_structure(db: Session, tmp_path: Path) -> None:
    pages = {
        1: "This page has ordinary prose.\nIt continues across two lines.\n1",
        2: "Maybe A Heading\n\nMore prose without any structure markers.\n2",
    }
    book = _make_book(db, tmp_path, "dd" * 32, pages)
    result = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()

    assert result.error is None
    assert result.chapters == []
    assert result.chapters_by_kind == {}
    assert result.front_matter_pages == []
    assert result.flagged_count == 1  # "Maybe A Heading" -- never a chapter
    assert result.section_count == 0
    assert result.subsection_count == 0
    assert result.paragraph_count == 2

    chapters = db.scalars(select(Chapter).where(Chapter.book_id == book.id)).all()
    assert chapters == []
    flagged = db.scalars(
        select(ContentBlock).where(
            ContentBlock.book_id == book.id, ContentBlock.block_type == BlockType.HEADING
        )
    ).all()
    assert len(flagged) == 1
    assert flagged[0].status == ContentStatus.REVIEW
    assert flagged[0].chapter is None


# ----------------------------------------------------------------- page handling


def test_blank_pages_from_index(db: Session, tmp_path: Path) -> None:
    sha = "ee" * 32
    root = tmp_path / "processed" / "extract" / sha
    _write_extract_with_index(
        tmp_path,
        sha,
        {1: "Chapter 1\nOpening text.\n", 2: None, 3: "Closing text.\n"},
    )
    pages = load_extract_pages(root)
    assert pages == {1: "Chapter 1\nOpening text.\n", 2: "", 3: "Closing text.\n"}

    source = SourceFile(sha256=sha, file_path=f"books/{sha}.pdf", format=SourceFormat.PDF)
    db.add(source)
    db.flush()
    book = Book(source_file_id=source.id, title="Indexed Book")
    db.add(book)
    db.flush()

    result = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()
    assert result.page_count == 3
    assert result.pages_with_text == 2
    page_rows = db.scalars(select(Page).where(Page.book_id == book.id)).all()
    assert len(page_rows) == 3
    by_no = {p.page_number: p.has_text for p in page_rows}
    assert by_no == {1: True, 2: False, 3: True}


def test_load_extract_pages_fallback(tmp_path: Path) -> None:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "0001.txt").write_text("one", encoding="utf-8")
    (pages_dir / "0003.txt").write_text("three", encoding="utf-8")
    assert load_extract_pages(tmp_path) == {1: "one", 3: "three"}


# ----------------------------------------------------------------- error paths


def test_detect_structure_missing_extract_fails(db: Session, tmp_path: Path) -> None:
    source = SourceFile(
        sha256="ff" * 32,
        file_path=f"books/{'ff' * 32}.pdf",
        format=SourceFormat.PDF,
    )
    db.add(source)
    db.flush()
    book = Book(source_file_id=source.id, title="No Extraction")
    db.add(book)
    db.flush()

    result = detect_structure(book, session=db, data_dir=tmp_path)
    db.flush()
    assert result.error and "no extraction output" in result.error
    assert result.page_count == 0
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.job_type == JobType.STRUCTURE))
    assert job is not None
    assert job.status.value == "failed"
    assert db.scalars(select(Chapter)).all() == []


def test_structure_render_report_text() -> None:
    from knowledge_base.pipeline.structure.processor import (
        StructureResult,
        render_report_text,
    )

    result = StructureResult(
        sha256="aa" * 32,
        source_file_id="4102c698-edd8-4e6d-9004-abcdef000001",
        book_id="bb" * 16,
        error="boom",
        page_count=3,
        pages_with_text=2,
        toc_pages=[1],
        chapters_by_kind={"chapter": 1, "table_of_contents": 1},
        paragraph_count=2,
        block_count=4,
        flagged_count=1,
        blocks_by_type={"paragraph": 2, "heading": 1, "toc_entry": 1},
        flagged_blocks=[{"page": 1, "note": "uncertain", "text": "Possible Heading"}],
    )
    text = render_report_text(result)
    assert "Pages: 2/3 with text" in text
    assert "Table of contents: pages [1]" in text
    assert "Chapters: 1 sections=0 subsections=0" in text
    assert "Paragraphs: 2 blocks=4 flagged=1" in text
    assert "Blocks by type: paragraph=2, heading=1, toc_entry=1" in text
    assert "p.1 [uncertain] Possible Heading" in text
    assert "Error: boom" in text
