"""Enumerations shared across the knowledge-base schema.

Values are stored in PostgreSQL by their ``.value`` (lowercase), not by enum
member name, to keep storage stable and renames safe.
"""

from __future__ import annotations

from enum import Enum


class SourceFormat(str, Enum):
    """Physical file formats accepted by the ingestion pipeline."""

    PDF = "pdf"
    EPUB = "epub"
    DOCX = "docx"
    TXT = "txt"
    HTML = "html"
    JSON = "json"


class SourceStatus(str, Enum):
    """Lifecycle status of a raw source file."""

    REGISTERED = "registered"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class JobType(str, Enum):
    """Pipeline stage carried out by a ProcessingJob."""

    INGEST = "ingest"
    INSPECT = "inspect"
    EXTRACT = "extract"
    OCR = "ocr"
    METADATA = "metadata"
    STRUCTURE = "structure"
    NORMALIZE = "normalize"
    CHUNK = "chunk"
    INDEX = "index"
    EMBED = "embed"
    VALIDATE = "validate"


class JobStatus(str, Enum):
    """Lifecycle status of a processing job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ContentStatus(str, Enum):
    """Review / validation status of derived content.

    Mirrors the pipeline: ``pending -> validated -> review -> published``,
    with ``quarantined`` reserved for rejected material.
    """

    PENDING = "pending"
    VALIDATED = "validated"
    REVIEW = "review"
    PUBLISHED = "published"
    QUARANTINED = "quarantined"


class BlockType(str, Enum):
    """Kind of a content block extracted from a source."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    VERSE = "verse"
    HADITH = "hadith"
    FOOTNOTE = "footnote"
    PAGE_HEADER = "page_header"
    OTHER = "other"


class Language(str, Enum):
    """Languages supported by the knowledge base."""

    ARABIC = "ar"
    URDU = "ur"
    ENGLISH = "en"
    OTHER = "other"


class LicenseType(str, Enum):
    """Distribution rights recorded for a source."""

    PUBLIC_DOMAIN = "public_domain"
    COPYRIGHTED = "copyrighted"
    CC_BY = "cc_by"
    CC_BY_SA = "cc_by_sa"
    CC_BY_NC = "cc_by_nc"
    OTHER = "other"
    UNKNOWN = "unknown"