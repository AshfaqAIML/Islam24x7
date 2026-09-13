"""OCR configuration for the knowledge base.

Kept engine-agnostic: the processor only relies on ``engine``, ``dpi``,
``languages`` and the quality thresholds below. Anything engine-specific
stays inside the backend implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OcrConfig:
    """Tunables for page rendering, OCR, and quality assessment."""

    engine: str = "tesseract"
    """Backend name: ``tesseract``, ``easyocr``, or ``dummy`` (tests)."""

    dpi: int = 300
    """Render resolution for pages fed to the OCR engine."""

    languages: tuple[str, ...] = ("ar",)
    """ISO 639-1 codes in engine-preferred order; combine for mixed docs, e.g. ``("en","ar")``."""

    tesseract_psm: int = 3  # Tesseract page-segmentation mode (auto).

    min_confidence: float = 50.0
    """Confidence (0-100) below which a page is flagged for review."""

    min_text_chars: int = 30
    """Pages with fewer non-whitespace characters are flagged for review."""

    min_alpha_ratio: float = 0.5
    """Minimum fraction of non-whitespace chars that are letters; below this the
    output is treated as symbol noise and flagged for review."""

    extra_tesseract_config: str = field(default="")
    """Optional raw Tesseract ``config`` string appended on every call."""


DEFAULT_OCR_CONFIG = OcrConfig()