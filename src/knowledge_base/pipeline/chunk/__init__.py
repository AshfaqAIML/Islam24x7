"""Stable-ID chunking of normalized text.

Splits normalized content into structure-aware, page-anchored chunks with
deterministic identifiers derived from the book position, so chunking is
stable and resumable while keeping book/chapter/section/page/source
provenance intact.
"""

from knowledge_base.pipeline.chunk.chunker import (
    Chunk,
    ParagraphUnit,
    build_chunks,
    make_chunk_id,
)
from knowledge_base.pipeline.chunk.config import ChunkConfig, estimate_tokens
from knowledge_base.pipeline.chunk.processor import ChunkResult, chunk_all, chunk_book

__all__ = [
    "Chunk",
    "ChunkConfig",
    "ChunkResult",
    "ParagraphUnit",
    "build_chunks",
    "chunk_all",
    "chunk_book",
    "estimate_tokens",
    "make_chunk_id",
]