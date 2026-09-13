"""Book metadata extraction pipeline.

Extracts candidate bibliographic fields from multiple evidence sources
(PDF metadata, filename, title page, first pages, and explicit operator
input), records them with confidence + uncertainty, merges them into a
best-guess report, and supports human review + publication. Never invents
metadata and never treats an automatically-extracted value as verified.
"""

from knowledge_base.pipeline.metadata.config import (
    DEFAULT_METADATA_CONFIG,
    MetadataConfig,
)
from knowledge_base.pipeline.metadata.extractors import extract_from_pages
from knowledge_base.pipeline.metadata.processor import (
    MetadataResult,
    PublishResult,
    apply_review,
    extract_metadata,
    extract_metadata_all,
    merge_candidates,
    overall_confidence,
    publish_metadata,
)

__all__ = [
    "DEFAULT_METADATA_CONFIG",
    "MetadataConfig",
    "MetadataResult",
    "PublishResult",
    "apply_review",
    "extract_metadata",
    "extract_metadata_all",
    "extract_from_pages",
    "merge_candidates",
    "overall_confidence",
    "publish_metadata",
]