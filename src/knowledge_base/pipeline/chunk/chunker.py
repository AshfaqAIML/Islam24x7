"""Structure-aware chunking of paragraphs into retrieval-ready chunks.

A chunk is a maximal run of consecutive paragraphs inside one section (or
chapter) that fits the token budget, plus optional overlap with the previous
chunk in the same section. Paragraphs are atomic; nothing ever splits across a
section or chapter boundary, and page spans are recorded per chunk.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from knowledge_base.database.enums import Language
from knowledge_base.pipeline.chunk.config import ChunkConfig

_JOIN_SEPARATOR = "\n\n"
_JOIN_TOKEN_COST = 2  # approximate cost of "\n\n" for budgeting


@dataclass(frozen=True)
class ParagraphUnit:
    """One atomic paragraph offered to the chunker."""

    block_id: str
    chapter_no: int | None
    section_no: int | None
    page: int | None
    sequence: int
    text: str
    tokens: int


@dataclass
class Chunk:
    """A structure-aware group of consecutive paragraphs."""

    block_ids: list[str]
    page_start: int | None
    page_end: int | None
    text: str
    token_count: int
    chunk_index: int
    chunk_id: str
    chapter_no: int | None
    section_no: int | None


def make_chunk_id(
    source_sha: str,
    chapter_no: int | None,
    section_no: int | None,
    first_page: int | None,
    chunk_index: int,
) -> str:
    """Deterministic stable id for a chunk.

    Keyed on the book position (chapter/section/start page + creation index)
    rather than row UUIDs, so re-running detection + chunking yields identical
    ids even when row ids change.
    """
    digest = hashlib.sha256(
        (
            f"{source_sha}:{chapter_no or 0}:{section_no or 0}:{first_page or 0}:{chunk_index}"
        ).encode()
    ).hexdigest()
    return digest[:96]


def _section_key(unit: ParagraphUnit) -> tuple[int | None, int | None]:
    return (unit.chapter_no, unit.section_no)


def _approx_tokens(units: list[ParagraphUnit]) -> int:
    """Token total of the joined chunk text (units + separators)."""
    if not units:
        return 0
    return sum(u.tokens for u in units) + _JOIN_TOKEN_COST * (len(units) - 1)


def _close_into(
    chunks: list[Chunk],
    units: list[ParagraphUnit],
    *,
    source_sha: str,
    chunk_index: int,
) -> None:
    text = _JOIN_SEPARATOR.join(u.text for u in units)
    pages = [u.page for u in units if u.page is not None]
    chunks.append(
        Chunk(
            block_ids=[u.block_id for u in units],
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            text=text,
            token_count=_approx_tokens(units),
            chunk_index=chunk_index,
            chunk_id=make_chunk_id(
                source_sha,
                units[0].chapter_no,
                units[0].section_no,
                min(pages) if pages else None,
                chunk_index,
            ),
            chapter_no=units[0].chapter_no,
            section_no=units[0].section_no,
        )
    )


def _tail_overlap_units(units: list[ParagraphUnit], budget: int) -> list[ParagraphUnit]:
    """Trailing whole paragraphs whose joint tokens fit ``budget`` (overlap)."""
    tail: list[ParagraphUnit] = []
    run = 0
    for unit in reversed(units):
        if run + unit.tokens > budget:
            break
        tail.append(unit)
        run += unit.tokens
    tail.reverse()
    return tail


def build_chunks(
    paragraphs: list[ParagraphUnit],
    *,
    source_sha: str,
    language: Language,
    config: ChunkConfig,
) -> list[Chunk]:
    """Group consecutive paragraphs into structure-aware chunks.

    Guarantees:
    * paragraphs are never split - an oversized paragraph becomes its own chunk;
    * a chunk never spans two sections/chapters, and no overlap bleeds across
      a section boundary;
    * chunks are emitted in book order with a deterministic running index.
    """
    chunks: list[Chunk] = []
    current: list[ParagraphUnit] = []
    current_key: tuple[int | None, int | None] | None = None
    current_tokens = 0
    index = 0

    for unit in paragraphs:
        key = _section_key(unit)

        if current and key != current_key:
            _close_into(chunks, current, source_sha=source_sha, chunk_index=index)
            index += 1
            current, current_tokens, current_key = [], 0, None

        if not current:
            current, current_tokens, current_key = [unit], unit.tokens, key
            continue

        if unit.tokens > config.max_tokens or (
            current_tokens + unit.tokens + _JOIN_TOKEN_COST > config.max_tokens
        ):
            _close_into(chunks, current, source_sha=source_sha, chunk_index=index)
            index += 1
            seed = [unit]
            if unit.tokens <= config.max_tokens:
                tail = _tail_overlap_units(current, config.overlap_tokens)
                primed = tail + [unit]
                if _approx_tokens(primed) <= config.max_tokens:
                    seed = primed
            current, current_tokens, current_key = seed, _approx_tokens(seed), key
        else:
            current.append(unit)
            current_tokens += unit.tokens + _JOIN_TOKEN_COST
            current_key = key

    _close_into(chunks, current, source_sha=source_sha, chunk_index=index)
    return chunks


__all__ = ["Chunk", "ParagraphUnit", "build_chunks", "make_chunk_id"]