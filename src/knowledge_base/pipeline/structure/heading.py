"""Heading detection: evidence-based chapter/section/subsection recognition.

Markers (``الباب``, ``الفصل``, ``Chapter``, ...), ordinals (Arabic ordinal
words, Arabic-Indic/Urdu digits, roman numerals) and dotted numbering
(``1.2.3``) are combined into a :class:`Heading` signal. Lines that merely
*look* like a heading are returned with ``uncertain=True`` so the processor
flags them for human review instead of fabricating structure.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from knowledge_base.database.enums import ChapterKind
from knowledge_base.pipeline.structure.config import StructureConfig

_ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
_URDU_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_DIGIT_TRANS = str.maketrans(_ARABIC_INDIC + _URDU_DIGITS, "0123456789" * 2)

_NUMBER_PREFIX = rf"[\d{_ARABIC_INDIC}{_URDU_DIGITS}]+"

# Sorted longest-first so ``الاول`` in ``الاول`` vs ``الاولى`` resolves.
_ORDINALS: dict[str, int] = {
    "الحادي": 11, "الحادى": 11, "الثاني عشر": 12, "الثانى عشر": 12,
    "الثالث عشر": 13, "الرابع عشر": 14, "الخامس عشر": 15,
    "السادس عشر": 16, "السابع عشر": 17, "الثامن عشر": 18,
    "التاسع عشر": 19, "العشرون": 20, "الثلاثون": 30, "الأربعون": 40,
    "اربعون": 40, "الخمسون": 50, "الستون": 60, "السبعون": 70,
    "الثمانون": 80, "التسعون": 90,
    "التاسع": 9, "الثامن": 8, "السابع": 7, "السادس": 6,
    "الخامس": 5, "الرابع": 4, "الثالث": 3, "الثاني": 2, "الثانى": 2,
    "الأول": 1, "الاول": 1, "أول": 1, "اول": 1, "اولى": 1, "الأولى": 1,
    "دهم": 10, "بيستم": 20, "چهارم": 4, "پنجم": 5, "پانجم": 5,
    "ششم": 6, "هفتم": 7, "هشتم": 8, "نهم": 9, "دوم": 2, "سوم": 3,
}
_TENS = {2: "العشرون", 3: "الثلاثون", 4: "الاربعون", 5: "الخمسون",
         6: "الستون", 7: "السبعون", 8: "الثمانون", 9: "التسعون"}

_ROMAN = re.compile(r"^(?=[MDCLXVI])M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_DOTTED_NUMBER = re.compile(
    rf"\s*[{_ARABIC_INDIC}{_URDU_DIGITS}0-9]+(?:\.\s*[{_ARABIC_INDIC}{_URDU_DIGITS}0-9]+)+"
)
_SENTENCE_END = ("،", "؛", ":", ".", "؟", "!", "?", "\u2014", "۔")


@dataclass(frozen=True)
class Heading:
    """A detected heading line."""

    level: int  # 1 chapter, 2 section, 3 subsection
    title: str
    kind: ChapterKind = ChapterKind.CHAPTER
    number: int | None = None
    references: bool = False
    confidence: str = "high"
    uncertain: bool = False
    evidence: str = ""


def normalize_arabic(text: str) -> str:
    """Lowercase Arabic/Urdu text with diacritics stripped for marker matching."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", text)
    text = text.replace("\u0640", "")  # tatweel
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    text = text.replace("ة", "ه").replace("ۀ", "ه")
    text = text.replace("ی", "ي").replace("ئ", "ي").replace("ؤ", "و").replace("ک", "ك")
    text = text.replace("ھ", "ه").replace("ہ", "ه").replace("ۃ", "ه")
    return text.lower()


def translate_digits(text: str) -> str:
    """Convert Arabic-Indic and Urdu digits to ASCII digits."""
    return text.translate(_DIGIT_TRANS)


# Lookups keyed by the same normalized form ``normalize_arabic`` produces so
# ordinals like ``الأولى`` resolve after harakat/letter normalisation.
_NORMALIZED_ORDINALS = {normalize_arabic(key): value for key, value in _ORDINALS.items()}
_TENS_BY_NORMALIZED = {
    normalize_arabic(literal): tens for tens, literal in _TENS.items()
}


def _ordinal_value(token: str) -> int | None:
    normalized = normalize_arabic(translate_digits(token)).strip()
    parts = [p for p in re.split(r"\s*و\s*", normalized) if p]
    if len(parts) == 2 and parts[1] in _TENS_BY_NORMALIZED:
        base = _NORMALIZED_ORDINALS.get(parts[0])
        if base is not None:
            return _TENS_BY_NORMALIZED[parts[1]] * 10 + (base % 10)
    return _NORMALIZED_ORDINALS.get(normalized)


def _strip_number_prefix(text: str) -> tuple[int | None, str]:
    """Pull a leading numeral/ordinal off ``text``; return (number, remainder)."""
    stripped = text.strip()
    digits_match = re.fullmatch(rf"{_NUMBER_PREFIX}+", stripped)
    if digits_match:
        return int(translate_digits(stripped)), ""
    ordinal = _ordinal_value(stripped)
    if ordinal is not None:
        return ordinal, ""
    match = re.match(rf"\s*({_NUMBER_PREFIX}+)\s*[.:\-–—]?\s+(.+)$", text)
    if match:
        return int(translate_digits(match.group(1))), match.group(2).strip()
    match = re.match(r"\s*([\u0640-ٿ\w]+)\s*[.:\-–—]?\s+(.+)$", text)
    if match:
        number = _ordinal_value(match.group(1))
        if number is not None:
            return number, match.group(2).strip()
    return None, stripped


def _marker_match(line: str, marker: str) -> bool:
    norm = normalize_arabic(line)
    marker_norm = normalize_arabic(marker)
    if not norm.startswith(marker_norm):
        return False
    rest = norm[len(marker_norm):]
    return not (rest and rest[0].isalnum())  # partial word such as ``فصلان``


def _original_prefix_end(line: str, norm: str, prefix_len: int) -> int:
    """Index in ``line`` where ``prefix_len`` normalized characters end.

    ``normalize_arabic`` may drop characters (harakat, tatweel) so the marker's
    position in the normalized form cannot be used to slice the original line.
    We walk the original line tracking the running normalized length instead.
    """
    if len(line) == len(norm):
        return prefix_len
    normalized = 0
    for i, char in enumerate(line):
        converted = normalize_arabic(char)
        if not converted:
            continue
        normalized += len(converted)
        if normalized >= prefix_len:
            return i + 1
    return len(line)


def _heading_from_marker(
    line: str,
    norm: str,
    marker: str,
    level: int,
    kind: ChapterKind,
    *,
    references: bool = False,
    source: str,
) -> Heading:
    if not _marker_match(line, marker):
        raise AssertionError("marker must match")
    marker_norm = normalize_arabic(marker)
    rest = line[_original_prefix_end(line, norm, len(marker_norm)):].strip()
    number, title = _strip_number_prefix(rest) if rest else (None, rest)
    title = title.strip(" .:-–—\u200f\u200e")
    if not title:
        title = line.strip()
    return Heading(
        level=level,
        title=title,
        kind=kind,
        number=number,
        references=references,
        confidence="high",
        uncertain=False,
        evidence=f"marker '{marker}' ({source})",
    )


def detect_heading(line: str, config: StructureConfig) -> Heading | None:
    """Return a Heading for a confident (marker/numbered) line, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 500:
        return None
    norm = normalize_arabic(line)

    for marker in config.appendix_markers:
        if _marker_match(line, marker):
            return _heading_from_marker(
                line, norm, marker, 1, ChapterKind.APPENDIX, source="appendix marker"
            )
    for marker in config.references_markers:
        if _marker_match(line, marker):
            return _heading_from_marker(
                line, norm, marker, 1, ChapterKind.CHAPTER, references=True,
                source="references marker",
            )
    for marker in config.chapter_markers:
        if _marker_match(line, marker):
            return _heading_from_marker(
                line, norm, marker, 1, ChapterKind.CHAPTER, source="chapter marker"
            )
    for marker in config.section_markers:
        if _marker_match(line, marker):
            return _heading_from_marker(
                line, norm, marker, 2, ChapterKind.CHAPTER, source="section marker"
            )
    for marker in config.subsection_markers:
        if _marker_match(line, marker):
            return _heading_from_marker(
                line, norm, marker, 3, ChapterKind.CHAPTER, source="subsection marker"
            )

    dotted = _DOTTED_NUMBER.match(stripped)
    if dotted:
        parts = [translate_digits(p) for p in re.split(r"\.", dotted.group(0).strip(" ,.:"))]
        digits = [p for p in parts if p.isdigit()]
        if len(digits) >= 2:
            depth = len(digits)
            title_after = stripped[dotted.end():].strip(" .:-–—\u200f\u200e")
            if depth >= config.dotted_depth_subsection:
                level = 3
            elif depth >= config.dotted_depth_section:
                level = 2
            else:
                level = 1
            return Heading(
                level=level,
                title=title_after or stripped,
                kind=ChapterKind.CHAPTER,
                confidence="high",
                uncertain=False,
                evidence="dotted numbering",
            )
    return None


def looks_like_heading_candidate(
    line: str, *, prev: str | None, next_: str | None, config: StructureConfig
) -> Heading | None:
    """Heuristic "possible heading" — always uncertain, reviewed by a human."""
    stripped = line.strip()
    if not stripped:
        return None
    words = stripped.split()
    if not (config.heading_fallback_min_words <= len(words) <= config.heading_fallback_max_words):
        return None
    if len(stripped) > config.heading_fallback_max_chars:
        return None
    if stripped.endswith(_SENTENCE_END):
        return None
    isolated = prev is not None and next_ is not None and not prev.strip() and not next_.strip()
    if not isolated:
        return None
    return Heading(
        level=0,
        title=stripped,
        kind=ChapterKind.CHAPTER,
        number=None,
        confidence="medium",
        uncertain=True,
        evidence="possible heading (isolated short line; review)",
    )


def is_roman_number(text: str) -> bool:
    return bool(_ROMAN.match(text.strip()))


__all__ = [
    "Heading",
    "detect_heading",
    "is_roman_number",
    "looks_like_heading_candidate",
    "normalize_arabic",
    "translate_digits",
]