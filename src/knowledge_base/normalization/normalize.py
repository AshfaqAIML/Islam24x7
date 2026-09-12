"""Core normalization logic.

Order of operations:

1. Collapse line-break variants (CRLF, CR, form feeds) to ``\\n`` and collapse
   runs of blank lines.
2. Apply Unicode normalization (NFC by default) to unify canonically-equivalent
   encodings without changing meaning.
3. Collapse runs of whitespace on each line and drop trailing spaces.
4. Remove tatweel (kashida ``U+0640``) — a purely presentational grapheme.
5. If enabled and the text is not protected religious content, apply
   conservative Arabic search folds and Urdu folds.

A text is *protected* when it contains any of the configured protected markers
(typically Quranic or hadith quotations); in that case all character-level
folding is skipped so religious wording is never altered. The original string is
always preserved verbatim on ``NormalizationResult.original``.
"""

from __future__ import annotations

import re
import unicodedata

from knowledge_base.normalization.models import (
    NormalizationConfig,
    NormalizationResult,
    NormalizationStats,
)

_TATWEEL = "\u0640"

# Arabic script character-level folds (search-oriented; all opt-in).
_HAMZA_SRC = "أؤإآ"
_HAMZA_DST = "اواا"
_ALEF_MAQSURA_SRC = "ى"
_ALEF_MAQSURA_DST = "ي"
_TEH_MARBUTA_SRC = "ة"
_TEH_MARBUTA_DST = "ه"
_URDU_SRC = "ھی"
_URDU_DST = "ہے"
_DIGIT_SRC = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
_DIGIT_DST = "01234567890123456789"

_WS_RUN = re.compile(r"[ \t\x0b\x0c\u00a0]+")
_CRLF = re.compile(r"\r\n|\r|\f")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _is_protected(text: str, config: NormalizationConfig) -> bool:
    if not config.protect_religious_quotations:
        return False
    return any(marker in text for marker in config.protected_markers)


def conservative_config() -> NormalizationConfig:
    """Return an ultra-conservative config: layout-only normalization.

    Applies line-break/whitespace cleanup, NFC, and tatweel removal. No
    character-level folding of any kind, and religious protection enabled.
    """
    return NormalizationConfig()


def normalize_text(text: str, config: NormalizationConfig | None = None) -> NormalizationResult:
    """Return both the verbatim original and a search-normalized variant.

    The original string is stored unchanged; only ``normalized`` may differ.
    """
    config = config or NormalizationConfig()
    original = text

    work = text
    stats = NormalizationStats(chars_before=len(original))

    # 1) line-break cleanup
    cleaned = 0
    work, n = _CRLF.subn("\n", work)
    cleaned += n
    work, n = _MULTI_BLANK.subn("\n\n", work)
    cleaned += n
    stats.linebreaks_cleaned = cleaned

    # 2) unicode normalization
    if config.unicode_form in ("NFC", "NFKC"):
        work = unicodedata.normalize(config.unicode_form, work)

    # 3) whitespace cleanup (collapse runs, strip trailing space per line)
    n_ws = 0

    def _ws_sub(_m: re.Match[str]) -> str:
        nonlocal n_ws
        n_ws += 1
        return " "

    lines = work.split("\n")
    collapsed = [_WS_RUN.sub(_ws_sub, line).rstrip(" \t") for line in lines]
    work = "\n".join(collapsed)
    stats.whitespace_collapsed = n_ws

    # 4) tatweel removal
    n_tt = work.count(_TATWEEL)
    stats.tatweel_removed = n_tt
    work = work.replace(_TATWEEL, "")

    # 5) protected religious text: no character folding at all
    protected = _is_protected(original, config)
    stats.protected = protected
    if not protected:
        work, stats = _apply_character_folds(work, config, stats)

    stats.chars_after = len(work)
    return NormalizationResult(original=original, normalized=work, config=config, stats=stats)


def _apply_character_folds(
    work: str, config: NormalizationConfig, stats: NormalizationStats
) -> tuple[str, NormalizationStats]:
    if config.arabic_normalization in ("hamza_alef", "full_no_harakat"):
        n_hamza = sum(work.count(ch) for ch in _HAMZA_SRC)
        stats.hamza_normalized = n_hamza
        work = work.translate(str.maketrans(_HAMZA_SRC, _HAMZA_DST))

    if config.arabic_normalization == "full_no_harakat":
        n_teh = work.count(_TEH_MARBUTA_SRC)
        stats.teh_marbuta_normalized = n_teh
        work = work.translate(str.maketrans(_TEH_MARBUTA_SRC, _TEH_MARBUTA_DST))

        n_ya = work.count(_ALEF_MAQSURA_SRC)
        stats.alef_maqsura_normalized = n_ya
        work = work.translate(str.maketrans(_ALEF_MAQSURA_SRC, _ALEF_MAQSURA_DST))

    if config.urdu_normalization:
        n_ur = sum(work.count(ch) for ch in _URDU_SRC)
        stats.urdu_folded = n_ur
        work = work.translate(str.maketrans(_URDU_SRC, _URDU_DST))

    if config.normalize_digits:
        n_digits = sum(work.count(ch) for ch in _DIGIT_SRC)
        stats.digits_normalized = n_digits
        work = work.translate(str.maketrans(_DIGIT_SRC, _DIGIT_DST))

    return work, stats
