"""Result model for search hits.

Every hit carries enough provenance to trace it back to the original content:
source file (sha256 + id), book / chapter / section ids and titles, page
number, and a domain-specific citation (chunk id, surah:ayah reference, or
collection hadith number).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    """One full-text search result across any supported domain."""

    domain: str
    rank: float
    title: str
    matched_text: str
    snippet: str
    language: str

    book: str | None = None
    author: str | None = None
    category: str | None = None
    chapter: str | None = None
    section: str | None = None
    page: int | None = None
    citation: str | None = None

    book_id: str | None = None
    chapter_id: str | None = None
    section_id: str | None = None
    source_file_id: str | None = None
    source_sha256: str | None = None
    chunk_id: str | None = None


__all__ = ["SearchHit"]