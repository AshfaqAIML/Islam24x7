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


class OcrStatus(str, Enum):
    """Per-page outcome of the OCR stage.

    ``ok`` means the engine returned text and it passed the quality checks.
    ``review`` means OCR ran but the output is suspicious (low confidence,
    very short, symbol-heavy, or empty) and needs human review — the page is
    never silently corrected or padded.
    ``failed`` means the engine errored and produced no usable text.
    """

    OK = "ok"
    REVIEW = "review"
    FAILED = "failed"


class PdfClassification(str, Enum):
    """How a PDF is classified by the inspection stage.

    ``TEXT_PDF`` has clean selectable text on (nearly) every page.
    ``SCANNED_PDF`` is image-only and must go through OCR.
    ``MIXED_PDF`` mixes text and scanned pages (or has enough blank pages
    that OCR is still needed for part of the book).
    ``INVALID_PDF`` cannot be read at all (corrupt, missing, encrypted).
    """

    TEXT_PDF = "text_pdf"
    SCANNED_PDF = "scanned_pdf"
    MIXED_PDF = "mixed_pdf"
    INVALID_PDF = "invalid_pdf"


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
    PAGE_NUMBER = "page_number"
    FRONT_MATTER = "front_matter"
    TOC_ENTRY = "toc_entry"
    REFERENCE = "reference"
    OTHER = "other"


class ChapterKind(str, Enum):
    """What a top-level container (``chapters`` row) represents.

    ``chapter`` is a real chapter of the work; the rest are structural regions
    the detector can identify so their content is still provenance-bound
    without being mistaken for the body text.
    """

    CHAPTER = "chapter"
    FRONT_MATTER = "front_matter"
    TABLE_OF_CONTENTS = "table_of_contents"
    APPENDIX = "appendix"


class Language(str, Enum):
    """Languages supported by the knowledge base."""

    ARABIC = "ar"
    URDU = "ur"
    ENGLISH = "en"
    OTHER = "other"


class MetadataField(str, Enum):
    """A bibliographic field the metadata stage can extract or review."""

    TITLE = "title"
    SUBTITLE = "subtitle"
    AUTHOR = "author"
    TRANSLATOR = "translator"
    EDITOR = "editor"
    PUBLISHER = "publisher"
    PUBLICATION_YEAR = "publication_year"
    EDITION = "edition"
    LANGUAGE = "language"
    ISBN = "isbn"
    CATEGORY = "category"
    DESCRIPTION = "description"
    PAGE_COUNT = "page_count"


class MetadataSource(str, Enum):
    """Where a metadata candidate came from (its provenance)."""

    PDF_METADATA = "pdf_metadata"
    FILENAME = "filename"
    FIRST_PAGES = "first_pages"
    TITLE_PAGE = "title_page"
    USER_PROVIDED = "user_provided"


class MetadataConfidence(str, Enum):
    """How strongly a metadata candidate is supported by its evidence.

    ``high`` — direct, marked evidence (PDF metadata title, a ``تأليف``
    line, an ISBN on the title page).
    ``medium`` — inferred from structure (language from script, a probable
    title line, a publication year without a marker).
    ``low`` — a guess that needs review (a title reconstructed from a
    filename slug).
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MetadataReviewStatus(str, Enum):
    """Human-review lifecycle of a metadata candidate.

    Nothing extracted automatically is ever treated as verified: candidates
    start ``pending`` (or ``review`` when uncertain), and only an explicit
    human decision moves one to ``approved`` (→ published) or ``rejected``.
    """

    PENDING = "pending"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


class LicenseType(str, Enum):
    """Distribution rights recorded for a source."""

    PUBLIC_DOMAIN = "public_domain"
    COPYRIGHTED = "copyrighted"
    CC_BY = "cc_by"
    CC_BY_SA = "cc_by_sa"
    CC_BY_NC = "cc_by_nc"
    OTHER = "other"
    UNKNOWN = "unknown"