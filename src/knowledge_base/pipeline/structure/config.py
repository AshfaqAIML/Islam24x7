"""Configurable rule sets for document structure detection.

The detector is intentionally rule-driven and evidence-based: it flags
uncertain signals for review instead of guessing at a book's layout. Every
book may use a different structure, so the marker vocabularies below are
plain data and can be tuned per collection without code changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StructureConfig:
    """Tunable thresholds and marker vocabularies for the detector."""

    # --- page / toc -----------------------------------------------------------
    toc_scan_pages: int = 8
    toc_min_lines: int = 3
    toc_line_ratio: float = 0.6
    toc_max_line_chars: int = 140

    # --- headings -------------------------------------------------------------
    chapter_markers: tuple[str, ...] = (
        "الباب", "باب", "الكتاب", "كتاب", "المجلد", "الجزء", "جزء",
        "القسم", "بخش", "part", "chapter",
    )
    section_markers: tuple[str, ...] = (
        "الفصل", "فصل", "مطلب", "مبحث", "عنوان", "section", "سبق",
    )
    subsection_markers: tuple[str, ...] = (
        "المسألة", "المسئلة", "مسألة", "مسئلة", "مسئله", "مسئلہ",
        "الفرع", "فرع", "مبحث", "subsection", "ذيل",
    )
    appendix_markers: tuple[str, ...] = (
        "الملحق", "ملحق", "المستدرك", "ضميمہ", "ضميمه", "ضمیمہ",
        "appendix", "annexe", "annex",
    )
    references_markers: tuple[str, ...] = (
        "المراجع", "المصادر", "الفهارس", "المصادر والمراجع",
        "فهرست المراجع", "فهرست", "bibliography", "references",
        "حوالہ جات", "حوالي", "ذخائر",
    )

    # A numbered heading with N dot-separated segments (``1.2``, ``1.2.3``)
    # maps to section/subsection depth below.
    dotted_depth_section: int = 2
    dotted_depth_subsection: int = 3

    # --- fallback "possible heading" (always flagged for review ---------------
    heading_fallback_min_words: int = 2
    heading_fallback_max_words: int = 14
    heading_fallback_max_chars: int = 90

    # --- page numbers / footnotes ---------------------------------------------
    page_number_max_chars: int = 4
    footnote_marker_re: str = (
        r"^\s*[\(（\[{]?\s*[\d٠-٩۰-۹]{1,3}[\)）\]}]?\s*[:\u200f\u200e]?\s*"
        r"[^\s.\d]"
    )
    footnote_star_re: str = r"^\s*\*{1,3}\s*[^\s]"
    footnote_separator_re: str = r"^\s*[_\-\u2500\u2014]{3,}\s*$"
    footnote_max_suffix_ratio: float = 0.35


DEFAULT_STRUCTURE_CONFIG = StructureConfig()


def page_number_regex(config: StructureConfig) -> re.Pattern[str]:
    """Compiled pattern for a standalone page-number line."""
    return re.compile(rf"^\s*[\d٠-٩۰-۹]{{1,{config.page_number_max_chars}}}\s*$")


def compile_regexes(
    config: StructureConfig,
) -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str], re.Pattern[str]]:
    """Return ``(page_number, footnote_marker, footnote_star, footnote_separator)``."""
    return (
        page_number_regex(config),
        re.compile(config.footnote_marker_re),
        re.compile(config.footnote_star_re),
        re.compile(config.footnote_separator_re),
    )


__all__ = ["DEFAULT_STRUCTURE_CONFIG", "StructureConfig", "compile_regexes", "page_number_regex"]