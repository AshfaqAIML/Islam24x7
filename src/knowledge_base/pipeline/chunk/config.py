"""Configuration for the structure-aware chunker.

Chunking is hierarchical: chapter -> section -> paragraph groups -> chunk.
Paragraphs are atomic (never split) and a chunk never crosses a section or
chapter boundary. ``max_tokens``/``overlap_tokens`` are the only tuning knobs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from knowledge_base.database.enums import Language


@dataclass(frozen=True)
class ChunkConfig:
    """Controls chunk size and overlap.

    ``max_tokens`` is a soft budget: a single paragraph that alone exceeds it
    is kept whole (paragraphs are never split). ``overlap_tokens`` repeats the
    trailing whole paragraphs of a chunk at the head of the next one (within
    the same section).
    """

    max_tokens: int = 512
    overlap_tokens: int = 64

    def __post_init__(self) -> None:
        if self.max_tokens < 16:
            raise ValueError("max_tokens must be >= 16")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be >= 0 and < max_tokens")


def estimate_tokens(text: str, language: Language) -> int:
    """Deterministic, script-aware token estimate for chunk budgeting.

    Heuristics (not a model): Arabic and Urdu scripts average ~3 chars/token,
    Latin ~4 chars/token. Precision is irrelevant for chunk sizing as long as
    it is stable, so re-runs and tests get identical budgets.
    """
    n = len(text)
    if language in (Language.ARABIC, Language.URDU):
        return max(1, math.ceil(n / 3))
    return max(1, math.ceil(n / 4))


__all__ = ["ChunkConfig", "estimate_tokens"]