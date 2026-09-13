"""Configuration for the metadata extraction stage."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetadataConfig:
    """Tuning knobs for metadata extraction.

    Fields extracted from the PDF text layer only make sense for files that
    actually have readable text (extraction/OCR fill that in for others).
    """

    #: How many leading pages to scan for title-page / first-pages signals.
    scan_first_pages: int = 5
    #: Whether a cleaned-up filename may seed a (low-confidence) title guess.
    use_filename: bool = True
    #: Longest filename stem worth considering as a title guess.
    filename_max_len: int = 120
    #: Source-priority used to break confidence ties when merging candidates
    #: (0 = weakest evidence, higher wins).
    source_priority: dict[str, int] = field(
        default_factory=lambda: {
            "filename": 1,
            "first_pages": 2,
            "title_page": 3,
            "pdf_metadata": 4,
            "user_provided": 5,
        }
    )
    #: Filename stems too generic to be a title guess (never invented).
    generic_stems: frozenset[str] = frozenset(
        {
            "book",
            "book1",
            "book2",
            "book3",
            "kitab",
            "كتاب",
            "document",
            "document1",
            "file",
            "scan",
            "scanned",
            "pdf",
            "image",
            "islam",
            "islamic",
            "slam",
            "untitled",
            "readme",
            "index",
            "notes",
            "license",
            "copying",
            "changelog",
            "تحریر",
        }
    )


DEFAULT_METADATA_CONFIG = MetadataConfig()


__all__ = ["DEFAULT_METADATA_CONFIG", "MetadataConfig"]