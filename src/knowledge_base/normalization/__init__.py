"""Normalization of extracted Islamic content for search purposes.

The pipeline keeps the original source text verbatim and produces a separate
search-normalized variant. It never replaces the original.
"""

from knowledge_base.normalization.models import (
    NormalizationConfig,
    NormalizationItem,
    NormalizationReport,
    NormalizationResult,
    NormalizationStats,
    search_config,
)
from knowledge_base.normalization.normalize import (
    conservative_config,
    normalize_text,
)
from knowledge_base.normalization.report import write_report

__all__ = [
    "NormalizationConfig",
    "NormalizationItem",
    "NormalizationReport",
    "NormalizationResult",
    "NormalizationStats",
    "conservative_config",
    "normalize_text",
    "search_config",
    "write_report",
]
