"""Universal source-provenance citations.

Every piece of searchable content — book chunks, ayahs/translations, hadiths —
can be reduced to a stable :class:`Citation` that traces it back to its
original source lineage:

    books:   Book -> Edition -> Chapter -> Section -> Page -> Content -> Chunk
    quran:   Quran -> Surah -> Ayah (-> Translation)
    hadith:  Collection -> Book -> Chapter -> Hadith

Citations are built **only** from loaded database records via function
:func:`citation_from_db` (or the typed ``citation_from_*`` builders); there is
no free-form API, so citations can never be invented by a caller or an LLM.
Every field is read back off the ORM row and its relationships, and a missing
relationship yields ``None``, never a fabricated value.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from sqlalchemy.orm import Session

from knowledge_base.database.models.hadith import Hadith
from knowledge_base.database.models.quran import Ayah, Translation
from knowledge_base.database.models.structure import Chapter, ContentChunk, Section

SOURCE_TYPES = ("book", "quran", "hadith")


@dataclass(frozen=True)
class Citation:
    """Stable, database-derived citation that locates one passage."""

    source_type: str

    # ----------------------------------------------------------------- book
    book_id: str | None = None
    book_title: str | None = None
    edition_id: str | None = None
    edition_title: str | None = None
    chapter_id: str | None = None
    chapter_title: str | None = None
    section_id: str | None = None
    section_title: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    page: int | None = None
    content_id: str | None = None
    chunk_id: str | None = None

    # ----------------------------------------------------------------- quran
    surah_id: str | None = None
    surah_number: int | None = None
    surah_name: str | None = None
    ayah_id: str | None = None
    ayah_number: int | None = None
    translation_language: str | None = None
    translator: str | None = None

    # ---------------------------------------------------------------- hadith
    collection_id: str | None = None
    collection_name: str | None = None
    hadith_book_id: str | None = None
    hadith_book_name: str | None = None
    hadith_chapter_id: str | None = None
    hadith_chapter_name: str | None = None
    hadith_id: str | None = None
    hadith_number: int | None = None

    # ---------------------------------------------------------------- origin
    source_file_id: str | None = None
    source_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        """JSON-serialisable mapping (stable key set, ``None`` for absent)."""
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def reference(self) -> str:
        """Compact human-readable reference for display strings."""
        if self.source_type == "quran":
            surah = self.surah_name or (
                str(self.surah_number) if self.surah_number is not None else "?"
            )
            base = f"{surah}:{self.ayah_number or '?'}"
            if self.translation_language:
                base += f" ({self.translation_language} by {self.translator or '?'})"
            return base
        if self.source_type == "hadith":
            parts: list[str] = []
            name = self.collection_name or self.collection_id
            parts.append(name or "collection")
            if self.hadith_number is not None:
                parts.append(f"#{self.hadith_number}")
            if self.hadith_book_name:
                parts.append(self.hadith_book_name)
            return " ".join(parts)
        parts = [self.book_title or self.book_id or "book"]
        if self.chapter_title:
            parts.append(f"ch. {self.chapter_title}")
        if self.section_title:
            parts.append(self.section_title)
        if self.page is not None:
            parts.append(f"p. {self.page}")
        if self.chunk_id:
            parts.append(self.chunk_id)
        return ", ".join(parts)


def _str(value: object | None) -> str | None:
    return str(value) if value is not None else None


def citation_from_chunk(chunk: ContentChunk) -> Citation:
    """Build a *book* citation from a database-loaded ``ContentChunk``."""
    if not isinstance(chunk, ContentChunk):
        raise TypeError(f"expected a ContentChunk record, got {type(chunk).__name__}")
    book = chunk.book
    edition = book.edition if book else None
    session = Session.object_session(chunk)
    chapter = None
    section = None
    if session is not None and chunk.chapter_id:
        chapter = session.get(Chapter, chunk.chapter_id)
    if session is not None and chunk.section_id:
        section = session.get(Section, chunk.section_id)
    sf = chunk.source_file
    return Citation(
        source_type="book",
        book_id=_str(book.id) if book else None,
        book_title=book.title if book else None,
        edition_id=_str(edition.id) if edition else None,
        edition_title=edition.title if edition else None,
        chapter_id=_str(chapter.id) if chapter else None,
        chapter_title=chapter.title if chapter else None,
        section_id=_str(section.id) if section else None,
        section_title=section.title if section else None,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        page=chunk.page_start or chunk.page_end,
        content_id=_str(chunk.id),
        chunk_id=chunk.chunk_id,
        source_file_id=_str(sf.id) if sf else None,
        source_sha256=sf.sha256 if sf else None,
    )


def citation_from_ayah(ayah: Ayah) -> Citation:
    """Build a *quran* citation from a database-loaded ``Ayah``."""
    if not isinstance(ayah, Ayah):
        raise TypeError(f"expected an Ayah record, got {type(ayah).__name__}")
    surah = ayah.surah
    sf = ayah.source_file
    return Citation(
        source_type="quran",
        surah_id=_str(surah.id) if surah else None,
        surah_number=surah.number if surah else None,
        surah_name=surah.name_arabic if surah else None,
        ayah_id=_str(ayah.id),
        ayah_number=ayah.number,
        page=ayah.page_number,
        source_file_id=_str(sf.id) if sf else None,
        source_sha256=sf.sha256 if sf else None,
    )


def citation_from_translation(translation: Translation) -> Citation:
    """Build a *quran* citation from a database-loaded ``Translation``."""
    if not isinstance(translation, Translation):
        raise TypeError(
            f"expected a Translation record, got {type(translation).__name__}"
        )
    base = citation_from_ayah(translation.ayah)
    return replace(
        base,
        translation_language=translation.language,
        translator=translation.translator,
    )


def citation_from_hadith(hadith: Hadith) -> Citation:
    """Build a *hadith* citation from a database-loaded ``Hadith``."""
    if not isinstance(hadith, Hadith):
        raise TypeError(f"expected a Hadith record, got {type(hadith).__name__}")
    collection = hadith.collection
    hbook = hadith.hadith_book
    hchapter = hadith.hadith_chapter
    sf = hadith.source_file
    return Citation(
        source_type="hadith",
        collection_id=_str(collection.id) if collection else None,
        collection_name=(collection.title or collection.name) if collection else None,
        hadith_book_id=_str(hbook.id) if hbook else None,
        hadith_book_name=hbook.name if hbook else None,
        hadith_chapter_id=_str(hchapter.id) if hchapter else None,
        hadith_chapter_name=hchapter.name if hchapter else None,
        hadith_id=_str(hadith.id),
        hadith_number=hadith.number,
        source_file_id=_str(sf.id) if sf else None,
        source_sha256=sf.sha256 if sf else None,
    )


def citation_from_db(record: object) -> Citation:
    """Build the citation for any supported database record.

    Supported records: ``ContentChunk``, ``Ayah``, ``Translation``,
    ``Hadith``. Anything else is rejected — citations originate only from
    actual database records.
    """
    if isinstance(record, ContentChunk):
        return citation_from_chunk(record)
    if isinstance(record, Ayah):
        return citation_from_ayah(record)
    if isinstance(record, Translation):
        return citation_from_translation(record)
    if isinstance(record, Hadith):
        return citation_from_hadith(record)
    raise TypeError(f"no citation exists for {type(record).__name__}")


__all__ = [
    "Citation",
    "citation_from_ayah",
    "citation_from_chunk",
    "citation_from_db",
    "citation_from_hadith",
    "citation_from_translation",
]