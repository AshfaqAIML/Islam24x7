"""Structure processor: detect and materialize a book's layout.

Consumes the extraction stage's output directory and produces the spine of a
published :class:`Book`:

    Book
    ├── front matter (chapters.kind = front_matter)   chapter 0
    ├── table of contents (kind = table_of_contents)  chapter -1
    └── chapters 1..N
          └── sections 1..N (reset per chapter)
                └── subsections 1..N (reset per section)
    pages 1..M -> paragraphs + content_blocks (typed)

Principles:

* Evidence wins. Only confident signals (markers, dotted numbering) create
  structural rows. Lines that merely look like headings are emitted as
  ``HEADING`` content blocks with ``status = review`` and a note, never as
  fabricated structure.
* Nothing is guessed silently. Running page-header repeats and page-number
  lines are suppressed and counted; every decision shows up in the report and
  ``ProcessingJob`` manifest.
* Idempotent. Re-running the detector rewrites the book's structure rows.

The pipeline is page-granular: ``pages`` come from the extract index — both
text and blank pages — so page numbers stay true to the physical source.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import (
    BlockType,
    ChapterKind,
    ContentStatus,
    JobStatus,
    JobType,
)
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Page,
    Paragraph,
    Section,
    Subsection,
)
from knowledge_base.logging import logger
from knowledge_base.pipeline.jobs import upsert_processing_job
from knowledge_base.pipeline.structure.config import (
    DEFAULT_STRUCTURE_CONFIG,
    StructureConfig,
    compile_regexes,
)
from knowledge_base.pipeline.structure.heading import (
    Heading,
    detect_heading,
    looks_like_heading_candidate,
    normalize_arabic,
    translate_digits,
)

_TRAILING_PAGE_NUMBER = re.compile(r"[\d٠-٩۰-۹]{1,4}\s*$")
_LEADER_DOTS = {".", "\u2026", "\u0092", "\u00b7", "\u2024"}


@dataclass
class StructureResult:
    """Outcome of detecting structure for one book."""

    sha256: str
    source_file_id: str
    book_id: str
    error: str | None = None
    extract_dir: Path | None = None
    report_path: Path | None = None
    page_count: int = 0
    pages_with_text: int = 0
    toc_pages: list[int] = field(default_factory=list)
    front_matter_pages: list[int] = field(default_factory=list)
    chapters: list[dict[str, object]] = field(default_factory=list)
    section_count: int = 0
    subsection_count: int = 0
    paragraph_count: int = 0
    block_count: int = 0
    flagged_count: int = 0
    suppressed_repeats: int = 0
    dropped_page_numbers: int = 0
    blocks_by_type: dict[str, int] = field(default_factory=dict)
    chapters_by_kind: dict[str, int] = field(default_factory=dict)
    flagged_blocks: list[dict[str, object]] = field(default_factory=list)


@dataclass
class _ChapterPlan:
    number: int
    kind: ChapterKind
    title: str
    references: bool = False
    opening_page: int = 0


@dataclass
class _SectionPlan:
    chapter_no: int
    number: int
    title: str
    opening_page: int = 0


@dataclass
class _SubsectionPlan:
    section_idx: int
    number: int
    title: str
    opening_page: int = 0


@dataclass
class _BlockPlan:
    page_no: int
    block_type: BlockType
    text: str
    status: ContentStatus
    notes: str | None
    chapter_no: int | None
    section_idx: int | None = None
    subsection_idx: int | None = None
    paragraph_row: bool = False


@dataclass
class _Element:
    kind: str  # "heading" | "paragraph" | "footnote" | "toc_entry"
    text: str
    heading: Heading | None = None
    block_type: BlockType | None = None


# --- page / toc helpers --------------------------------------------------------


def load_extract_pages(extract_dir: Path) -> dict[int, str]:
    """Return ``{page_number: text}`` for every physical page.

    Uses ``index.json`` (full enumeration with blanks) when present, falling
    back to the ``pages/*.txt`` glob so tests and hand-made outputs work too.
    """
    pages: dict[int, str] = {}
    index = extract_dir / "index.json"
    if index.is_file():
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for entry in data.get("page_files", []):
            try:
                page = int(entry["page"])
            except (KeyError, TypeError, ValueError):
                continue
            name = entry.get("file")
            if name:
                path = extract_dir / "pages" / name
                pages[page] = path.read_text(encoding="utf-8") if path.is_file() else ""
            else:
                pages[page] = ""
    if not pages:
        pages_dir = extract_dir / "pages"
        if pages_dir.is_dir():
            for path in sorted(pages_dir.glob("*.txt")):
                try:
                    page = int(path.stem)
                except ValueError:
                    continue
                pages[page] = path.read_text(encoding="utf-8")
    return pages


def _is_page_number(line: str, max_chars: int) -> bool:
    return bool(re.match(rf"\d{{1,{max_chars}}}$", translate_digits(line.strip())))


def _leader_dot_count(line: str) -> int:
    return sum(1 for ch in line if ch in _LEADER_DOTS)


def looks_like_toc_line(line: str, config: StructureConfig) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > config.toc_max_line_chars:
        return False
    if _leader_dot_count(stripped) >= 3:
        return True
    return bool(_TRAILING_PAGE_NUMBER.search(re.sub(r"\s", "", stripped)))


def classify_toc_pages(pages: dict[int, str], config: StructureConfig) -> set[int]:
    """Pages in the leading region that read like a table of contents."""
    toc: set[int] = set()
    for page_no, text in sorted(pages.items()):
        if page_no > config.toc_scan_pages:
            break
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            continue
        body = [ln for ln in lines if not _is_page_number(ln, config.page_number_max_chars)]
        if len(body) < config.toc_min_lines:
            continue
        toc_count = sum(1 for ln in body if looks_like_toc_line(ln, config))
        if toc_count >= config.toc_min_lines and toc_count / len(body) >= config.toc_line_ratio:
            toc.add(page_no)
    return toc


# --- segmentation --------------------------------------------------------------


def _is_basmala(line: str) -> bool:
    lowered = line.strip().lower()
    return (
        lowered.startswith("بسم")
        or lowered.startswith("بِسْم")
        or lowered.startswith("بسملہ")
        or lowered == "الرحمن الرحيم"
        or "بِسْمِ اللَّهِ" in lowered
    )


def _starts_footnote(line: str, patterns: tuple[Any, ...]) -> bool:
    page_num, marker, star, separator = patterns
    if not line.strip():
        return False
    if page_num.match(line):
        return False
    return bool(marker.match(line) or star.match(line) or separator.match(line))


def segment_page(
    text: str,
    config: StructureConfig,
    patterns: tuple[Any, ...],
    *,
    page_no: int,
    is_toc: bool,
) -> tuple[list[_Element], int]:
    """Split one page's text into elements; returns (elements, page_numbers_dropped)."""
    elements: list[_Element] = []
    dropped = 0
    lines = text.splitlines()
    i = 0
    net = len(lines)
    while i < net:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        if _is_page_number(stripped, config.page_number_max_chars):
            dropped += 1
            i += 1
            continue

        if is_toc:
            elements.append(_Element("toc_entry", raw, block_type=BlockType.TOC_ENTRY))
            i += 1
            continue

        if _starts_footnote(stripped, patterns):
            buf = [raw]
            j = i + 1
            while j < net and lines[j].strip():
                if _is_page_number(lines[j].strip(), config.page_number_max_chars):
                    dropped += 1
                    j += 1
                    continue
                buf.append(lines[j])
                j += 1
            elements.append(_Element("footnote", "\n".join(buf), block_type=BlockType.FOOTNOTE))
            i = j
            continue

        heading = detect_heading(raw, config)
        if heading is not None:
            elements.append(_Element("heading", raw, heading, BlockType.HEADING))
            i += 1
            continue

        prev_line = lines[i - 1] if i > 0 else ""
        next_line = lines[i + 1] if i + 1 < net else ""
        candidate = looks_like_heading_candidate(
            stripped, prev=prev_line, next_=next_line, config=config
        )
        if candidate is not None and not _is_basmala(stripped):
            elements.append(_Element("heading", raw, candidate, BlockType.HEADING))
            i += 1
            continue

        buf = [raw]
        j = i + 1
        while j < net and lines[j].strip():
            if _is_page_number(lines[j].strip(), config.page_number_max_chars):
                dropped += 1
                j += 1
                continue
            if _starts_footnote(lines[j].strip(), patterns):
                break
            if detect_heading(lines[j], config) is not None:
                break
            buf.append(lines[j])
            j += 1
        elements.append(_Element("paragraph", "\n".join(buf), block_type=BlockType.PARAGRAPH))
        i = j
    return elements, dropped


def _repeat_of_open(
    heading: Heading,
    chapter: _ChapterPlan | None,
    section: _SectionPlan | None,
    subsection: _SubsectionPlan | None,
    page_no: int,
) -> bool:
    """Running page headers repeat the title of the element currently open."""
    norm = normalize_arabic(heading.title)
    if heading.level == 1:
        if chapter is None or chapter.opening_page >= page_no:
            return False
        return normalize_arabic(chapter.title) == norm
    if heading.level == 2:
        if section is None or section.opening_page >= page_no:
            return False
        return normalize_arabic(section.title) == norm
    if heading.level == 3:
        if subsection is None or subsection.opening_page >= page_no:
            return False
        return normalize_arabic(subsection.title) == norm
    return False


# --- planning ------------------------------------------------------------------


class _Plans:
    def __init__(self) -> None:
        self.chapters: list[_ChapterPlan] = []
        self.sections: list[_SectionPlan] = []
        self.subsections: list[_SubsectionPlan] = []
        self.blocks: list[_BlockPlan] = []
        self.dropped_page_numbers = 0
        self.suppressed_repeats = 0
        self.paragraph_count = 0
        self.blocks_by_type: dict[str, int] = {}
        self.chapters_by_kind: dict[str, int] = {}
        self.flagged_blocks: list[dict[str, object]] = []


def _append_block(
    plans: _Plans,
    page_no: int,
    block_type: BlockType,
    text: str,
    *,
    status: ContentStatus,
    notes: str | None,
    chapter_no: int | None,
    section_idx: int | None = None,
    subsection_idx: int | None = None,
    paragraph_row: bool = False,
) -> None:
    plans.blocks.append(
        _BlockPlan(
            page_no=page_no,
            block_type=block_type,
            text=text,
            status=status,
            notes=notes,
            chapter_no=chapter_no,
            section_idx=section_idx,
            subsection_idx=subsection_idx,
            paragraph_row=paragraph_row,
        )
    )
    plans.blocks_by_type[block_type.value] = plans.blocks_by_type.get(block_type.value, 0) + 1
    if paragraph_row:
        plans.paragraph_count += 1


def _section_index(section: _SectionPlan | None, plans: _Plans) -> int | None:
    if section is None:
        return None
    for idx, candidate in enumerate(plans.sections):
        if candidate is section:
            return idx
    return None


def _subsection_index(subsection: _SubsectionPlan | None, plans: _Plans) -> int | None:
    if subsection is None:
        return None
    for idx, candidate in enumerate(plans.subsections):
        if candidate is subsection:
            return idx
    return None


def _flag_orphan(
    plans: _Plans,
    element: _Element,
    page_no: int,
    note: str,
) -> None:
    plans.flagged_blocks.append(
        {
            "page": page_no,
            "block_type": BlockType.HEADING.value,
            "text": element.text,
            "note": note,
        }
    )
    _append_block(
        plans,
        page_no,
        BlockType.HEADING,
        element.text,
        status=ContentStatus.REVIEW,
        notes=note,
        chapter_no=None,
    )


def _build_plans(
    pages: dict[int, str],
    *,
    config: StructureConfig,
    patterns: tuple[Any, ...],
    toc_pages: set[int],
    front_pages: list[int],
) -> _Plans:
    plans = _Plans()
    body_chapter_number = 0
    section_number = 0
    subsection_number = 0
    current_chapter: _ChapterPlan | None = None
    current_section: _SectionPlan | None = None
    current_subsection: _SubsectionPlan | None = None
    in_references = False
    front_plan: _ChapterPlan | None = None
    toc_plan: _ChapterPlan | None = None
    front_active = bool(front_pages)
    front_set: set[int] = set(front_pages)

    def ensure_toc() -> _ChapterPlan:
        nonlocal toc_plan
        if toc_plan is None:
            toc_plan = _ChapterPlan(-1, ChapterKind.TABLE_OF_CONTENTS, "(table of contents)")
            plans.chapters.append(toc_plan)
            plans.chapters_by_kind[toc_plan.kind.value] = (
                plans.chapters_by_kind.get(toc_plan.kind.value, 0) + 1
            )
        return toc_plan

    def ensure_front() -> _ChapterPlan:
        nonlocal front_plan
        if front_plan is None:
            front_plan = _ChapterPlan(0, ChapterKind.FRONT_MATTER, "(front matter)")
            plans.chapters.append(front_plan)
            plans.chapters_by_kind[front_plan.kind.value] = (
                plans.chapters_by_kind.get(front_plan.kind.value, 0) + 1
            )
        return front_plan

    def open_chapter(
        kind: ChapterKind, title: str, page_no: int, *, references: bool = False
    ) -> _ChapterPlan:
        nonlocal body_chapter_number, section_number, subsection_number
        body_chapter_number += 1
        plan = _ChapterPlan(
            body_chapter_number, kind, title, references=references, opening_page=page_no
        )
        plans.chapters.append(plan)
        plans.chapters_by_kind[kind.value] = plans.chapters_by_kind.get(kind.value, 0) + 1
        return plan

    for page_no in sorted(pages):
        text = pages[page_no]
        if not text.strip():
            continue
        is_toc = page_no in toc_pages
        is_front = front_active and page_no in front_set
        elements, dropped = segment_page(
            text, config, patterns, page_no=page_no, is_toc=is_toc
        )
        plans.dropped_page_numbers += dropped

        for element in elements:
            if element.kind == "heading":
                heading = element.heading
                assert heading is not None
                if heading.uncertain:
                    plans.flagged_blocks.append(
                        {
                            "page": page_no,
                            "block_type": BlockType.HEADING.value,
                            "text": element.text,
                            "note": heading.evidence,
                        }
                    )
                    _append_block(
                        plans,
                        page_no,
                        BlockType.HEADING,
                        element.text,
                        status=ContentStatus.REVIEW,
                        notes=heading.evidence,
                        chapter_no=current_chapter.number if current_chapter else None,
                        section_idx=_section_index(current_section, plans),
                        subsection_idx=_subsection_index(current_subsection, plans),
                    )
                    continue

                if _repeat_of_open(
                    heading,
                    current_chapter,
                    current_section,
                    current_subsection,
                    page_no,
                ):
                    plans.suppressed_repeats += 1
                    continue

                if heading.kind == ChapterKind.APPENDIX or heading.references or heading.level == 1:
                    chapter_kind = (
                        ChapterKind.APPENDIX
                        if heading.kind == ChapterKind.APPENDIX
                        else ChapterKind.CHAPTER
                    )
                    current_chapter = open_chapter(
                        chapter_kind,
                        heading.title,
                        page_no,
                        references=heading.references,
                    )
                    current_section = None
                    current_subsection = None
                    section_number = 0
                    subsection_number = 0
                    in_references = heading.references
                    _append_block(
                        plans,
                        page_no,
                        BlockType.HEADING,
                        element.text,
                        status=ContentStatus.VALIDATED,
                        notes=heading.evidence,
                        chapter_no=current_chapter.number,
                    )
                    continue

                if heading.level == 2:
                    if (
                        current_chapter is None
                        or current_chapter.kind not in (ChapterKind.CHAPTER, ChapterKind.APPENDIX)
                    ):
                        _flag_orphan(
                            plans, element, page_no, "section heading before any chapter"
                        )
                        continue
                    chapter_no = current_chapter.number
                    section_number += 1
                    number = heading.number if heading.number is not None else section_number
                    section_number = max(section_number, number)
                    current_section = _SectionPlan(
                        chapter_no, number, heading.title, opening_page=page_no
                    )
                    plans.sections.append(current_section)
                    current_subsection = None
                    subsection_number = 0
                    _append_block(
                        plans,
                        page_no,
                        BlockType.HEADING,
                        element.text,
                        status=ContentStatus.VALIDATED,
                        notes=heading.evidence,
                        chapter_no=chapter_no,
                        section_idx=_section_index(current_section, plans),
                    )
                    continue

                if heading.level == 3:
                    section_idx = _section_index(current_section, plans)
                    if current_chapter is None or current_section is None or section_idx is None:
                        _flag_orphan(
                            plans, element, page_no, "subsection heading without an open section"
                        )
                        continue
                    chapter_no = current_chapter.number
                    subsection_number += 1
                    number = (
                        heading.number if heading.number is not None else subsection_number
                    )
                    subsection_number = max(subsection_number, number)
                    current_subsection = _SubsectionPlan(
                        section_idx,
                        number,
                        heading.title,
                        opening_page=page_no,
                    )
                    plans.subsections.append(current_subsection)
                    _append_block(
                        plans,
                        page_no,
                        BlockType.HEADING,
                        element.text,
                        status=ContentStatus.VALIDATED,
                        notes=heading.evidence,
                        chapter_no=chapter_no,
                        section_idx=section_idx,
                        subsection_idx=_subsection_index(current_subsection, plans),
                    )
                    continue

            if element.kind == "toc_entry":
                _append_block(
                    plans,
                    page_no,
                    BlockType.TOC_ENTRY,
                    element.text,
                    status=ContentStatus.VALIDATED,
                    notes=None,
                    chapter_no=ensure_toc().number,
                )
                continue

            if element.kind == "paragraph":
                if is_front:
                    _append_block(
                        plans,
                        page_no,
                        BlockType.FRONT_MATTER,
                        element.text,
                        status=ContentStatus.VALIDATED,
                        notes=None,
                        chapter_no=ensure_front().number,
                    )
                    continue
                if (
                    current_chapter is None
                    or current_chapter.kind not in (ChapterKind.CHAPTER, ChapterKind.APPENDIX)
                ):
                    _append_block(
                        plans,
                        page_no,
                        BlockType.PARAGRAPH,
                        element.text,
                        status=ContentStatus.VALIDATED,
                        notes=None,
                        chapter_no=None,
                        paragraph_row=True,
                    )
                    continue
                chapter_no = current_chapter.number
                block_type = BlockType.REFERENCE if in_references else BlockType.PARAGRAPH
                _append_block(
                    plans,
                    page_no,
                    block_type,
                    element.text,
                    status=ContentStatus.VALIDATED,
                    notes=None,
                    chapter_no=chapter_no,
                    section_idx=_section_index(current_section, plans),
                    subsection_idx=_subsection_index(current_subsection, plans),
                    paragraph_row=block_type == BlockType.PARAGRAPH,
                )
                continue

            if element.kind == "footnote":
                _append_block(
                    plans,
                    page_no,
                    BlockType.FOOTNOTE,
                    element.text,
                    status=ContentStatus.VALIDATED,
                    notes=None,
                    chapter_no=current_chapter.number if current_chapter else None,
                    section_idx=_section_index(current_section, plans),
                    subsection_idx=_subsection_index(current_subsection, plans),
                )
                continue
    return plans


# --- materialization -----------------------------------------------------------


def _materialize(
    book: Book, plans: _Plans, pages: dict[int, str], session: Session
) -> None:
    """Idempotently replace the book's structure rows with the new plans."""
    book_id = book.id
    source_file_id = book.source_file_id

    session.execute(delete(ContentChunk).where(ContentChunk.book_id == book_id))
    session.execute(delete(ContentBlock).where(ContentBlock.book_id == book_id))
    session.execute(delete(Paragraph).where(Paragraph.book_id == book_id))
    session.execute(delete(Page).where(Page.book_id == book_id))
    session.execute(delete(Subsection).where(Subsection.book_id == book_id))
    session.execute(delete(Section).where(Section.book_id == book_id))
    session.execute(delete(Chapter).where(Chapter.book_id == book_id))
    session.flush()

    chapters_by_no: dict[int, Chapter] = {}
    for chapter_plan in plans.chapters:
        chapter = Chapter(
            id=uuid.uuid4(),
            book_id=book_id,
            number=chapter_plan.number,
            title=chapter_plan.title,
            kind=chapter_plan.kind,
            source_file_id=source_file_id,
        )
        session.add(chapter)
        chapters_by_no[chapter_plan.number] = chapter

    sections_by_idx: dict[int, Section] = {}
    for idx, section_plan in enumerate(plans.sections):
        try:
            chapter_owner = chapters_by_no[section_plan.chapter_no]
        except KeyError:
            raise AssertionError(
                f"section references unknown chapter {section_plan.chapter_no}"
            ) from None
        section = Section(
            id=uuid.uuid4(),
            book_id=book_id,
            chapter_id=chapter_owner.id,
            number=section_plan.number,
            title=section_plan.title,
            source_file_id=source_file_id,
        )
        session.add(section)
        sections_by_idx[idx] = section

    subsections_by_idx: dict[int, Subsection] = {}
    for idx, subsection_plan in enumerate(plans.subsections):
        try:
            section_owner = sections_by_idx[subsection_plan.section_idx]
        except KeyError:
            raise AssertionError(
                f"subsection references unknown section {subsection_plan.section_idx}"
            ) from None
        subsection = Subsection(
            id=uuid.uuid4(),
            book_id=book_id,
            section_id=section_owner.id,
            number=subsection_plan.number,
            title=subsection_plan.title,
            source_file_id=source_file_id,
        )
        session.add(subsection)
        subsections_by_idx[idx] = subsection

    pages_by_no: dict[int, Page] = {}
    for page_no in sorted(pages):
        page = Page(
            id=uuid.uuid4(),
            book_id=book_id,
            source_file_id=source_file_id,
            page_number=page_no,
            has_text=bool(pages[page_no].strip()),
        )
        session.add(page)
        pages_by_no[page_no] = page

    sequence_by_page: dict[int, int] = {}
    for block in plans.blocks:
        seq = sequence_by_page.get(block.page_no, 0) + 1
        sequence_by_page[block.page_no] = seq
        blk_page = pages_by_no.get(block.page_no)
        blk_chapter = (
            chapters_by_no.get(block.chapter_no) if block.chapter_no is not None else None
        )
        blk_section = (
            sections_by_idx.get(block.section_idx) if block.section_idx is not None else None
        )
        blk_subsection = (
            subsections_by_idx.get(block.subsection_idx)
            if block.subsection_idx is not None
            else None
        )
        session.add(
            ContentBlock(
                id=uuid.uuid4(),
                book_id=book_id,
                page_id=blk_page.id if blk_page else None,
                chapter_id=blk_chapter.id if blk_chapter else None,
                section_id=blk_section.id if blk_section else None,
                subsection_id=blk_subsection.id if blk_subsection else None,
                source_file_id=source_file_id,
                block_type=block.block_type,
                sequence=seq,
                original_text=block.text,
                status=block.status,
                notes=block.notes,
            )
        )
        if block.paragraph_row:
            session.add(
                Paragraph(
                    id=uuid.uuid4(),
                    book_id=book_id,
                    page_id=blk_page.id if blk_page else None,
                    source_file_id=source_file_id,
                    sequence=seq,
                    text=block.text,
                )
            )


# --- main entry ----------------------------------------------------------------


def detect_structure(
    book: Book,
    *,
    session: Session,
    data_dir: Path,
    config: StructureConfig | None = None,
) -> StructureResult:
    """Detect + materialize structure for one published book (idempotent)."""
    config = config or DEFAULT_STRUCTURE_CONFIG
    source_file = book.source_file
    sha256 = source_file.sha256
    result = StructureResult(
        sha256=sha256,
        source_file_id=str(source_file.id),
        book_id=str(book.id),
    )
    extract_dir = (data_dir.resolve() / "processed" / "extract" / sha256).resolve()

    pages = load_extract_pages(extract_dir)
    if not pages:
        result.error = f"no extraction output at {extract_dir}"
        _write_reports(result, _report_dir(data_dir))
        _upsert_job(session, result)
        return result

    patterns = compile_regexes(config)
    toc_pages = classify_toc_pages(pages, config)
    first_real = _first_real_chapter_page(pages, config, toc_pages)
    front_pages: list[int] = []
    if first_real is not None:
        front_pages = [
            page_no
            for page_no in sorted(pages)
            if page_no not in toc_pages and pages[page_no].strip() and page_no < first_real
        ]

    result.toc_pages = sorted(toc_pages)
    result.front_matter_pages = front_pages
    result.page_count = max(pages)
    result.pages_with_text = sum(1 for text in pages.values() if text.strip())

    plans = _build_plans(
        pages,
        config=config,
        patterns=patterns,
        toc_pages=toc_pages,
        front_pages=front_pages,
    )
    _materialize(book, plans, pages, session)

    result.dropped_page_numbers = plans.dropped_page_numbers
    result.suppressed_repeats = plans.suppressed_repeats
    result.block_count = len(plans.blocks)
    result.paragraph_count = plans.paragraph_count
    result.section_count = len(plans.sections)
    result.subsection_count = len(plans.subsections)
    result.chapters = [
        {"number": c.number, "kind": c.kind.value, "title": c.title, "references": c.references}
        for c in plans.chapters
    ]
    result.blocks_by_type = dict(sorted(plans.blocks_by_type.items()))
    result.chapters_by_kind = dict(sorted(plans.chapters_by_kind.items()))
    result.flagged_blocks = plans.flagged_blocks
    result.flagged_count = len(plans.flagged_blocks)
    if plans.flagged_blocks:
        logger.warning(
            "structure {} flagged {} block(s) for review", sha256[:12], len(plans.flagged_blocks)
        )

    _write_reports(result, _report_dir(data_dir))
    _upsert_job(session, result)
    return result


def _first_real_chapter_page(
    pages: dict[int, str], config: StructureConfig, toc_pages: set[int]
) -> int | None:
    """First page holding a confident level-1 chapter/appendix heading."""
    for page_no in sorted(pages):
        if page_no in toc_pages:
            continue
        for line in pages[page_no].splitlines():
            heading = detect_heading(line, config)
            if heading is not None and not heading.uncertain and heading.level == 1:
                return page_no
    return None


# --- reports -------------------------------------------------------------------


def _report_dir(data_dir: Path) -> Path:
    return data_dir.resolve() / "processed" / "structure"


def _write_reports(result: StructureResult, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "source": {
            "sha256": result.sha256,
            "book_id": result.book_id,
            "source_file_id": result.source_file_id,
        },
        "pages": {
            "total": result.page_count,
            "with_text": result.pages_with_text,
            "toc": result.toc_pages,
            "front_matter": result.front_matter_pages,
        },
        "structure": {
            "chapters": result.chapters,
            "sections": result.section_count,
            "subsections": result.subsection_count,
            "paragraphs": result.paragraph_count,
            "blocks": result.block_count,
        },
        "blocks_by_type": result.blocks_by_type,
        "chapters_by_kind": result.chapters_by_kind,
        "suppressed_repeats": result.suppressed_repeats,
        "dropped_page_numbers": result.dropped_page_numbers,
        "flagged_blocks": result.flagged_blocks,
        "error": result.error,
        "detected_at": datetime.now(UTC).isoformat(),
    }
    json_path = report_dir / f"{result.sha256}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.report_path = json_path
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = report_dir / f"{result.sha256}.txt"
    summary_path.write_text(render_report_text(result), encoding="utf-8")


def render_report_text(result: StructureResult) -> str:
    lines = [f"Structure for {result.sha256[:12]} (book {result.book_id[:8]})"]
    lines.append(f"Pages: {result.pages_with_text}/{result.page_count} with text")
    if result.toc_pages:
        lines.append(f"Table of contents: pages {result.toc_pages}")
    if result.front_matter_pages:
        lines.append(f"Front matter: pages {result.front_matter_pages}")
    lines.append(
        f"Chapters: {result.chapters_by_kind.get('chapter', 0)}"
        f" sections={result.section_count} subsections={result.subsection_count}"
    )
    lines.append(
        f"Paragraphs: {result.paragraph_count} blocks={result.block_count}"
        f" flagged={result.flagged_count}"
    )
    if result.blocks_by_type:
        lines.append(
            "Blocks by type: "
            + ", ".join(f"{key}={value}" for key, value in result.blocks_by_type.items())
        )
    if result.suppressed_repeats:
        lines.append(f"Suppressed header repeats: {result.suppressed_repeats}")
    if result.dropped_page_numbers:
        lines.append(f"Dropped page-number lines: {result.dropped_page_numbers}")
    if result.flagged_blocks:
        lines.append("Flagged for review:")
        for block in result.flagged_blocks:
            text = str(block["text"]).replace("\n", " ")
            if len(text) > 60:
                text = text[:60] + "…"
            lines.append(f"  p.{block['page']} [{block['note']}] {text}")
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines) + "\n"


def _upsert_job(session: Session, result: StructureResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.STRUCTURE,
        status=status,
        manifest={
            "page_count": result.page_count,
            "pages_with_text": result.pages_with_text,
            "toc_pages": result.toc_pages,
            "front_matter_pages": result.front_matter_pages,
            "chapters": len(result.chapters),
            "sections": result.section_count,
            "subsections": result.subsection_count,
            "paragraphs": result.paragraph_count,
            "blocks": result.block_count,
            "flagged": result.flagged_count,
            "blocks_by_type": result.blocks_by_type,
            "chapters_by_kind": result.chapters_by_kind,
            "report": result.report_path.name if result.report_path else None,
        },
        error=result.error,
    )


def detect_structure_all(
    session: Session,
    *,
    settings: Settings | None = None,
    config: StructureConfig | None = None,
    limit: int | None = None,
) -> list[StructureResult]:
    """Detect structure for every published book (idempotent)."""
    if settings is None:
        settings = get_settings()
    config = config or DEFAULT_STRUCTURE_CONFIG
    books = session.scalars(select(Book).order_by(Book.created_at)).all()
    if limit is not None:
        books = books[:limit]
    results: list[StructureResult] = []
    for book in books:
        logger.info("structure book={} {}", book.title, book.id)
        results.append(
            detect_structure(book, session=session, data_dir=settings.data_dir, config=config)
        )
    return results


__all__ = [
    "StructureResult",
    "classify_toc_pages",
    "detect_structure",
    "detect_structure_all",
    "load_extract_pages",
    "looks_like_toc_line",
    "render_report_text",
    "segment_page",
]