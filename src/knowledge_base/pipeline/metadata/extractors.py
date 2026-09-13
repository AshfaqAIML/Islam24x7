"""Metadata extractors: evidence-driven field extraction from multiple sources.

Every extractor is pure and read-only. It returns :class:`CandidateExtract`
objects carrying confidence, an ``uncertain`` flag, and the evidence they were
based on. **Nothing is invented**: when a signal is ambiguous (a filename slug,
a probable title line, a bare date) the candidate is marked ``uncertain`` with
medium/low confidence and left for human review.

Sources supported:

- ``pdf_metadata`` — PDF info dict (title, author, subject→description)
- ``filename``   — a cleaned-up slug seeding a low-confidence *title* guess
- ``title_page`` — marker-based fields on the first text-bearing page
- ``first_pages``— marker fields and language/date heuristics over the scan
- ``user_provided``— explicit facts from the operator (highest confidence)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from knowledge_base.database.enums import (
    MetadataConfidence,
    MetadataField,
    MetadataSource,
)
from knowledge_base.pipeline.inspect.inspect import detect_script_hint
from knowledge_base.pipeline.metadata.config import MetadataConfig

# utf-8 marker sets; a marker only fires when it starts a line (or is followed
# by a separator), so words like ``الطبعةالثانية`` without a gap still match
# but unrelated terms like ``دارفورد`` never do.
_AUTHOR_MARKERS = (
    "تأليف", "تألیف", "تاليف", "تالیف", "المؤلف", "المولف", "by",
)
_EDITOR_MARKERS = (
    "تحقيق", "تحقیق", "المحقق", "تصحيح", "تصحیح", "مصحح", "المصحح", "edited by",
)
_TRANSLATOR_MARKERS = (
    "ترجمة", "ترجمه", "مترجم", "المترجم", "translated by",
)
_PUBLISHER_MARKERS = (
    "مطبعة", "مطبعه", "المطبعة", "دار", "مكتبة", "مکتبة", "ناشر", "پریس", "لرتب", "publisher",
)
_EDITION_MARKERS = ("الطبعة", "الطبعه", "الطبعة")
_MARKER_FIELDS: list[tuple[tuple[str, ...], MetadataField]] = [
    (_AUTHOR_MARKERS, MetadataField.AUTHOR),
    (_EDITOR_MARKERS, MetadataField.EDITOR),
    (_TRANSLATOR_MARKERS, MetadataField.TRANSLATOR),
    (_PUBLISHER_MARKERS, MetadataField.PUBLISHER),
    (_EDITION_MARKERS, MetadataField.EDITION),
]

_YEAR_KEYLINE_WORDS = (
    "هجری", "هجري", "قمری", "قمرے", "سنة", "سنه", "سال", "ھ", "هـ", "۱۹", "۲۰",
)
_FIELD_ALIASES = {
    "title": MetadataField.TITLE,
    "author": MetadataField.AUTHOR,
    "translator": MetadataField.TRANSLATOR,
    "editor": MetadataField.EDITOR,
    "subtitle": MetadataField.SUBTITLE,
    "publisher": MetadataField.PUBLISHER,
    "publication year": MetadataField.PUBLICATION_YEAR,
    "publication_year": MetadataField.PUBLICATION_YEAR,
    "year": MetadataField.PUBLICATION_YEAR,
    "edition": MetadataField.EDITION,
    "language": MetadataField.LANGUAGE,
    "isbn": MetadataField.ISBN,
    "category": MetadataField.CATEGORY,
    "description": MetadataField.DESCRIPTION,
    "page count": MetadataField.PAGE_COUNT,
    "page_count": MetadataField.PAGE_COUNT,
}

_ASCII_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_HIJRI_RE = re.compile(r"(\d{3,4})\s*[هھ]ـ?")
_YEAR4_RE = re.compile(r"(?<!\d)(1[2-9]\d{2}|2\d{3})(?!\d)")
_VOLUME_RE = re.compile(
    r"(?:^|[-_. ])(vol|volume|juz|juz\'|juzo)[-_. ]*(\d+)(?:[-_. ]*)$", re.IGNORECASE
)


@dataclass(frozen=True)
class CandidateExtract:
    """One extracted metadata fact and how confident we are in it."""

    field: MetadataField
    value: str
    confidence: MetadataConfidence
    uncertain: bool
    source: MetadataSource
    evidence: str | None = None

    def __post_init__(self) -> None:
        value = " ".join(self.value.split())
        object.__setattr__(self, "value", value)


def parse_field(name: str) -> MetadataField:
    """Resolve a user-supplied field name / alias to a ``MetadataField``."""
    key = name.strip().lower()
    try:
        return MetadataField(key)
    except ValueError:
        pass
    try:
        return _FIELD_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unknown metadata field: {name!r}") from exc


def _clean_value(text: str) -> str:
    value = re.sub(r"^[\s\-–—؛،:؛;\u200f\u200e]+", "", text)
    value = re.sub(r"[\s\-؛،:؛;\u200f\u200e]+$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _marker_value(lines: list[str], index: int, marker: str) -> str:
    rest = _clean_value(lines[index][len(marker):])
    if rest:
        return rest
    for j in range(index + 1, min(index + 4, len(lines))):
        if lines[j].strip():
            return _clean_value(lines[j])
    return ""


def _is_page_number(line: str) -> bool:
    return bool(_PAGE_NUMBER_RE.match(line.translate(_ASCII_DIGITS)))


def _is_basmala(line: str) -> bool:
    lowered = line.strip().lower()
    return (
        lowered.startswith("بسم")
        or lowered.startswith("بِسْم")
        or lowered.startswith("بسملہ")
        or lowered == "الرحمن الرحيم"
        or "بِسْمِ اللَّهِ" in lowered
    )


def extract_from_pdf_metadata(meta: dict[str, str]) -> list[CandidateExtract]:
    """PDF info-dict → title, author (high); subject → description (medium)."""
    results: list[CandidateExtract] = []
    title = _clean_value(meta.get("title", ""))
    if title:
        results.append(
            CandidateExtract(
                MetadataField.TITLE, title, MetadataConfidence.HIGH, False,
                MetadataSource.PDF_METADATA, "pdf info title",
            )
        )
    author = _clean_value(meta.get("author", ""))
    if author:
        results.append(
            CandidateExtract(
                MetadataField.AUTHOR, author, MetadataConfidence.HIGH, False,
                MetadataSource.PDF_METADATA, "pdf info author",
            )
        )
    subject = _clean_value(meta.get("subject", ""))
    if subject:
        results.append(
            CandidateExtract(
                MetadataField.DESCRIPTION, subject, MetadataConfidence.MEDIUM, False,
                MetadataSource.PDF_METADATA, "pdf info subject",
            )
        )
    return results


def extract_from_filename(filename: str, config: MetadataConfig) -> list[CandidateExtract]:
    """Clean filename slug → low-confidence title guess (volume exclusions)."""
    if not config.use_filename:
        return []
    stem = Path(filename).stem.strip()
    if not stem:
        return []
    results: list[CandidateExtract] = []

    volume = _VOLUME_RE.search(stem)
    if volume:
        results.append(
            CandidateExtract(
                MetadataField.EDITION, f"Vol. {volume.group(2)}", MetadataConfidence.MEDIUM,
                False, MetadataSource.FILENAME, f"filename: {filename}",
            )
        )
        title = re.sub(
            r"(?:^|[-_. ])(vol|volume|juz|juz\'|juzo)[-_. ]*\d+(?:[-_. ]*)$",
            " ", stem, flags=re.IGNORECASE,
        )
    else:
        title = stem

    title = " ".join(title.replace("_", " ").replace(".", " ").replace("-", " ").split())
    if (
        len(title) >= 3
        and len(title) <= config.filename_max_len
        and title.lower() not in config.generic_stems
        and not title.isdigit()
    ):
        results.append(
            CandidateExtract(
                MetadataField.TITLE, title, MetadataConfidence.LOW, True,
                MetadataSource.FILENAME, f"filename: {filename}",
            )
        )
    return results


def extract_from_pages(
    page_texts: list[tuple[int, str]], config: MetadataConfig
) -> list[CandidateExtract]:
    """Scan first pages / title page for marked fields, dates, ISBNs, title."""
    pages = [(page_no, text) for page_no, text in page_texts if text]
    results: list[CandidateExtract] = []

    consumed: dict[int, set[int]] = {}
    for page_no, text in pages:
        lines = [ln.strip() for ln in text.splitlines()]
        for index, line in enumerate(lines):
            if not line:
                continue
            for markers, field in _MARKER_FIELDS:
                matched = _match_marker(line, markers)
                if matched is None:
                    continue
                if field == MetadataField.EDITION:
                    value = _clean_value(line)
                else:
                    value = _marker_value(lines, index, matched)
                if not value:
                    continue
                consumed.setdefault(page_no, set()).add(index)
                is_title_page = page_no == pages[0][0]
                source = (
                    MetadataSource.TITLE_PAGE if is_title_page else MetadataSource.FIRST_PAGES
                )
                results.append(
                    CandidateExtract(
                        field, value, MetadataConfidence.HIGH, False, source,
                        f"page {page_no} marker {matched!r}: {line.strip()}",
                    )
                )
                break

    year = _detect_year(pages)
    if year is not None:
        results.append(year)
    isbn = _detect_isbn(pages)
    if isbn is not None:
        results.append(isbn)

    title = _title_guess(pages, consumed)
    if title is not None:
        results.append(title)

    script = detect_script_hint("\n".join(text for _, text in page_texts))
    if script:
        results.append(
            CandidateExtract(
                MetadataField.LANGUAGE, script, MetadataConfidence.MEDIUM, False,
                MetadataSource.FIRST_PAGES, "script of first pages",
            )
        )
    return results


def _match_marker(line: str, markers: tuple[str, ...]) -> str | None:
    for marker in markers:
        if not line.startswith(marker):
            continue
        rest = line[len(marker):]
        if rest and (rest[0].isalnum() or rest[0].isalpha()):
            continue
        return marker
    return None


def _title_guess(
    pages: list[tuple[int, str]], consumed: dict[int, set[int]]
) -> CandidateExtract | None:
    for page_no, text in pages:
        lines = [ln.strip() for ln in text.splitlines()]
        candidates: list[str] = []
        for index, line in enumerate(lines):
            if not line:
                continue
            if index in consumed.get(page_no, set()):
                continue
            if _is_page_number(line) or _is_basmala(line):
                continue
            if len(line) < 3 or len(line) > 250:
                continue
            candidates.append(line)
        if not candidates:
            continue
        best = max(candidates, key=lambda ln: (len(ln), ln.lower()))
        return CandidateExtract(
            MetadataField.TITLE, best, MetadataConfidence.MEDIUM, True,
            MetadataSource.TITLE_PAGE, f"probable title line (page {page_no}): {best}",
        )
    return None


def _detect_year(pages: list[tuple[int, str]]) -> CandidateExtract | None:
    first_plain: CandidateExtract | None = None
    for page_no, text in pages:
        for raw in text.splitlines():
            line = raw.strip().translate(_ASCII_DIGITS)
            hijri = _HIJRI_RE.search(line)
            if hijri and 100 <= int(hijri.group(1)) <= 1699:
                digits = int(hijri.group(1))
                return CandidateExtract(
                    MetadataField.PUBLICATION_YEAR, f"{digits} (AH)",
                    MetadataConfidence.HIGH, False, MetadataSource.TITLE_PAGE,
                    f"hijri year on page {page_no}: {raw.strip()}",
                )
            match = _YEAR4_RE.search(line)
            if not match:
                continue
            year = int(match.group(1))
            keyword = any(word in line for word in _YEAR_KEYLINE_WORDS)
            if keyword:
                return CandidateExtract(
                    MetadataField.PUBLICATION_YEAR, str(year), MetadataConfidence.HIGH,
                    False, MetadataSource.TITLE_PAGE,
                    f"publication year on page {page_no}: {raw.strip()}",
                )
            if first_plain is None:
                first_plain = CandidateExtract(
                    MetadataField.PUBLICATION_YEAR, str(year), MetadataConfidence.MEDIUM,
                    True, MetadataSource.FIRST_PAGES,
                    f"possible year on page {page_no}: {raw.strip()}",
                )
    return first_plain


def _detect_isbn(pages: list[tuple[int, str]]) -> CandidateExtract | None:
    for page_no, text in pages:
        for raw in text.splitlines():
            marked = re.search(r"ISBN\s*[:：]?\s*([0-9][0-9Xx0-9\s\-–—]{8,16})", raw, re.IGNORECASE)
            if marked:
                digits = re.sub(r"[^0-9Xx]", "", marked.group(1))
                if len(digits) in (10, 13):
                    return CandidateExtract(
                        MetadataField.ISBN, digits, MetadataConfidence.HIGH, False,
                        MetadataSource.TITLE_PAGE, f"isbn on page {page_no}: {raw.strip()}",
                    )
        bare = re.search(r"(?<!\d)97[89][0-9]{10}(?!\d)", text.translate(_ASCII_DIGITS))
        if bare:
            return CandidateExtract(
                MetadataField.ISBN, bare.group(0), MetadataConfidence.HIGH, False,
                MetadataSource.FIRST_PAGES, f"bare isbn-13 on page {page_no}",
            )
    return None


def extract_from_user(items: list[tuple[str, str]]) -> list[CandidateExtract]:
    """Explicit operator facts: high confidence, never uncertain."""
    results: list[CandidateExtract] = []
    for name, value in items:
        field = parse_field(name)
        value = " ".join(str(value).split())
        if not value:
            continue
        results.append(
            CandidateExtract(
                field, value, MetadataConfidence.HIGH, False,
                MetadataSource.USER_PROVIDED, "user-provided metadata",
            )
        )
    return results


__all__ = [
    "CandidateExtract",
    "extract_from_filename",
    "extract_from_pages",
    "extract_from_pdf_metadata",
    "extract_from_user",
    "parse_field",
]