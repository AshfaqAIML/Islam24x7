"""Pydantic models for the normalization pipeline.

Central invariant: ``original`` is always retained verbatim; ``normalized`` is a
separate search-oriented variant and is never used to overwrite the source.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UnicodeForm = Literal["none", "NFC", "NFKC"]
ArabicNormalizationStyle = Literal["none", "hamza_alef", "full_no_harakat"]


class NormalizationConfig(BaseModel):
    """Configuration controlling how text is normalized.

    Defaults are deliberately conservative because the input is Islamic
    religious content. Character-level transformations (harakat removal,
    hamza/alef-maksura folding) are OFF unless explicitly enabled, and are
    additionally skipped whenever the text is flagged as protected religious
    content.
    """

    model_config = ConfigDict(frozen=True)

    unicode_form: UnicodeForm = "NFC"
    collapse_whitespace: bool = True
    collapse_linebreaks: bool = True
    remove_tatweel: bool = True

    # Arabic character-level normalization (search-oriented). All OFF by default.
    arabic_normalization: ArabicNormalizationStyle = "none"
    normalize_digits: bool = False

    # Urdu letters keep distinct identity; only generic script-neutral NFC applies.
    # When enabled, folds HEH DOACHASHMEE and YE variants conservatively.
    urdu_normalization: bool = False

    # Religious-content protection: when a protected marker is present,
    # character-level transformations are skipped for the whole text.
    protect_religious_quotations: bool = True
    protected_markers: tuple[str, ...] = (
        "\ufdf2",  # ﷽ (basmala, U+FDF2)
        "\ufd3f",  # ﴿ opening quranic ornament
        "\ufd3e",  # ﴾ closing quranic ornament
        "\ufdfa",  # ﷺ (salla llahu 'alayhi wa-sallam)
        "\ufdfb",  # ﷻ
        "بسم الله",
        "قال رسول الله",
        "رواه",
    )


class NormalizationStats(BaseModel):
    """Counters describing what the normalization run changed."""

    chars_before: int = 0
    chars_after: int = 0
    linebreaks_cleaned: int = 0
    whitespace_collapsed: int = 0
    tatweel_removed: int = 0
    harakat_removed: int = 0
    hamza_normalized: int = 0
    alef_maqsura_normalized: int = 0
    teh_marbuta_normalized: int = 0
    urdu_folded: int = 0
    digits_normalized: int = 0
    protected: bool = False

    @property
    def unchanged(self) -> bool:
        return self.chars_before == self.chars_after


class NormalizationResult(BaseModel):
    """Result for one piece of text: original and search-normalized variants."""

    original: str
    normalized: str
    config: NormalizationConfig = Field(default_factory=NormalizationConfig)
    stats: NormalizationStats = Field(default_factory=NormalizationStats)

    @property
    def unchanged(self) -> bool:
        return self.original == self.normalized


class NormalizationItem(BaseModel):
    """A normalized page-level item retaining its provenance coordinates."""

    source_file_id: str
    page_number: int
    text: str
    result: NormalizationResult


class NormalizationReport(BaseModel):
    """Aggregate normalization report for one source file."""

    source_file_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    items: list[NormalizationItem] = Field(default_factory=list)

    @property
    def changed_items(self) -> int:
        return sum(not item.result.unchanged for item in self.items)

    @property
    def protected_items(self) -> int:
        return sum(item.result.stats.protected for item in self.items)


def default_config() -> NormalizationConfig:
    """Return the conservative default configuration."""
    return NormalizationConfig()


def search_config() -> NormalizationConfig:
    """Return a search-oriented configuration with safe character folds.

    Harakat (diacritics) are still never removed — that step is too risky for
    religious text and must remain a deliberate, per-corpus decision.
    """
    return NormalizationConfig(
        arabic_normalization="hamza_alef",
        normalize_digits=True,
    )
