"""Normalize pipeline stage (production): derive search-normalized text."""

from knowledge_base.pipeline.normalize.processor import (
    NormalizeResult,
    book_language,
    normalize_all,
    normalize_book,
    resolve_config,
)

__all__ = [
    "NormalizeResult",
    "book_language",
    "normalize_all",
    "normalize_book",
    "resolve_config",
]