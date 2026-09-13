"""Normalize pipeline stage: produce search-normalized text for content blocks.

Reads the structured content a book produced (``content_blocks``), derives a
search-normalized variant per paragraph via :mod:`knowledge_base.normalization`,
and persists only that variant in ``normalized_texts``. ``original_text`` is
never touched; each row stores the SHA-256 of the original it was derived from
so provenance stays verifiable.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.database.enums import BlockType, JobStatus, JobType, Language
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.normalization import NormalizedText
from knowledge_base.database.models.structure import ContentBlock, Page
from knowledge_base.logging import logger
from knowledge_base.normalization import (
    NormalizationConfig,
    conservative_config,
    normalize_text,
    search_config,
)
from knowledge_base.pipeline.jobs import upsert_processing_job

# Only body prose is normalized for search. Religious, structural, reference
# and footnote blocks are intentionally left untouched (never even folded).
NORMALIZABLE_BLOCK_TYPES = frozenset({BlockType.PARAGRAPH})

_LANGUAGE_BY_NAME = {
    "ar": Language.ARABIC,
    "ara": Language.ARABIC,
    "arabic": Language.ARABIC,
    "ur": Language.URDU,
    "urd": Language.URDU,
    "urdu": Language.URDU,
    "en": Language.ENGLISH,
    "eng": Language.ENGLISH,
    "english": Language.ENGLISH,
}


@dataclass
class NormalizeResult:
    """Outcome of normalizing one book's content."""

    sha256: str
    book_id: str
    source_file_id: str
    error: str | None = None
    report_path: Path | None = None
    language: Language = Language.OTHER
    config_name: str = "conservative"
    blocks_total: int = 0
    blocks_normalized: int = 0
    blocks_skipped: int = 0
    blocks_protected: int = 0
    changed: int = 0
    unchanged: int = 0
    stats: dict[str, int] = field(default_factory=dict)


def book_language(book: Book) -> Language:
    """Map the book's stored language string onto a Language enum."""
    raw = (book.language or "").strip().lower()
    return _LANGUAGE_BY_NAME.get(raw, Language.OTHER)


def resolve_config(
    config_name: str, language: Language
) -> tuple[str, NormalizationConfig]:
    """Pick the effective config; ``config_name != 'auto'`` wins, else a
    per-language conservative default."""
    if config_name == "conservative":
        return "conservative", conservative_config()
    if config_name == "search":
        return "search", search_config()
    # auto
    if language == Language.ARABIC:
        # hamza/alef folding is the standard Arabic search fold; religious
        # content is still protected by NormalizationConfig.
        return "search", search_config()
    if language == Language.URDU:
        # conservative letters; numerals normalized so digit variants match.
        return "urdu", NormalizationConfig(normalize_digits=True)
    return "conservative", conservative_config()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_blocks(session: Session, book_id: str) -> list[ContentBlock]:
    return list(
        session.scalars(
            select(ContentBlock)
            .join(Page, ContentBlock.page_id == Page.id)
            .where(ContentBlock.book_id == book_id)
            .order_by(Page.page_number, ContentBlock.sequence)
        )
    )


def _render_report_text(
    result: NormalizeResult, lang_label: str, config_label: str
) -> str:
    lines = [f"Normalization for {result.sha256[:12]} (book {result.book_id[:8]})"]
    lines.append(f"Language: {lang_label}  config: {config_label}")
    lines.append(
        f"Blocks: total={result.blocks_total} normalized={result.blocks_normalized}"
        f" skipped={result.blocks_skipped} protected={result.blocks_protected}"
    )
    lines.append(f"Changed={result.changed} unchanged={result.unchanged}")
    if result.stats:
        lines.append(
            "Aggregate: "
            + ", ".join(f"{key}={value}" for key, value in result.stats.items())
        )
    if result.error:
        lines.append(f"Error: {result.error}")
    return "\n".join(lines) + "\n"


def normalize_book(
    book: Book,
    *,
    session: Session,
    data_dir: Path,
    config_name: str = "auto",
) -> NormalizeResult:
    """Derive (and persist) search-normalized text for every body paragraph.

    Idempotent: replaces the book's rows in ``normalized_texts``. Never
    modifies ``content_blocks.original_text``.
    """
    source_file = book.source_file
    sha256 = source_file.sha256
    result = NormalizeResult(
        sha256=sha256,
        book_id=str(book.id),
        source_file_id=str(source_file.id),
    )
    book_id = str(book.id)
    language = book_language(book)
    result.language = language

    blocks = _load_blocks(session, book_id)
    result.blocks_total = len(blocks)
    if not blocks:
        result.error = "book has no content blocks; did structure detection run?"
        result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
        _write_report(result, data_dir)
        _upsert_job(session, result)
        return result

    config_label, config = resolve_config(config_name, language)
    result.config_name = config_label

    session.execute(delete(NormalizedText).where(NormalizedText.book_id == book_id))
    session.flush()

    aggregate: dict[str, int] = {}
    for block in blocks:
        if block.block_type not in NORMALIZABLE_BLOCK_TYPES:
            result.blocks_skipped += 1
            continue
        res = normalize_text(block.original_text, config)
        result.blocks_normalized += 1
        if res.stats.protected:
            result.blocks_protected += 1
        if res.unchanged:
            result.unchanged += 1
        else:
            result.changed += 1
        for key, value in res.stats.model_dump().items():
            if isinstance(value, bool):
                continue
            aggregate[key] = aggregate.get(key, 0) + int(value)
        session.add(
            NormalizedText(
                content_block_id=block.id,
                book_id=book_id,
                source_file_id=source_file.id,
                language=language,
                config_name=config_label,
                normalized_text=res.normalized,
                original_sha256=_sha256(block.original_text),
                protected=res.stats.protected,
                stats=res.stats.model_dump(),
            )
        )
    result.stats = dict(sorted(aggregate.items()))
    result.report_path = _report_dir(data_dir) / f"{sha256}.txt"
    _write_report(result, data_dir)
    _upsert_job(session, result)
    return result


def normalize_all(
    session: Session,
    *,
    settings: Settings | None = None,
    config_name: str = "auto",
    limit: int | None = None,
) -> list[NormalizeResult]:
    """Normalize every published book (idempotent)."""
    if settings is None:
        settings = get_settings()
    books = session.scalars(select(Book).order_by(Book.created_at)).all()
    if limit is not None:
        books = books[:limit]
    results: list[NormalizeResult] = []
    for book in books:
        logger.info("normalize book={} {}", book.title, book.id)
        results.append(
            normalize_book(
                book,
                session=session,
                data_dir=settings.data_dir,
                config_name=config_name,
            )
        )
    return results


def _report_dir(data_dir: Path) -> Path:
    return data_dir.resolve() / "processed" / "normalized"


def _write_report(result: NormalizeResult, data_dir: Path) -> None:
    assert result.report_path is not None
    result.report_path.parent.mkdir(parents=True, exist_ok=True)
    text = _render_report_text(
        result, result.language.value, result.config_name
    )
    result.report_path.write_text(text, encoding="utf-8")


def _upsert_job(session: Session, result: NormalizeResult) -> None:
    status = JobStatus.SUCCEEDED if result.error is None else JobStatus.FAILED
    upsert_processing_job(
        session,
        source_file_id=uuid.UUID(result.source_file_id),
        job_type=JobType.NORMALIZE,
        status=status,
        manifest={
            "language": result.language.value,
            "config": result.config_name,
            "blocks_total": result.blocks_total,
            "blocks_normalized": result.blocks_normalized,
            "blocks_skipped": result.blocks_skipped,
            "blocks_protected": result.blocks_protected,
            "changed": result.changed,
            "unchanged": result.unchanged,
            "stats": result.stats,
            "report": result.report_path.name if result.report_path else None,
        },
        error=result.error,
    )


__all__ = [
    "NormalizeResult",
    "book_language",
    "normalize_all",
    "normalize_book",
    "resolve_config",
]