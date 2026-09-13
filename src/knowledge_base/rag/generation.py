"""Grounded answer generation.

Generation is deliberately simple and safe: the generator receives the
retrieved passages (labeled ``[S1]``, ``[S2]``, …) and the user question, and
returns text that must cite those markers. :func:`verify_grounding` then:

* rejects markers that point past the available sources,
* measures what fraction of answer sentences carry a marker, and
* flags the answer as ``grounded`` only above ``min_grounded_fraction``.

The built-in :class:`ExtractiveGenerator` needs no external model — it quotes
the passages directly, so it is guaranteed grounded and useful offline/for
tests. Any LLM provider can plug in behind :class:`AnswerGenerator`.
"""

from __future__ import annotations

import re
from typing import Protocol

from knowledge_base.rag.config import DEFAULT_RAG_CONFIG, RagConfig
from knowledge_base.rag.models import RetrievedSource

_MARKER_RE = re.compile(r"\[(S\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。「」])\s+")


class AnswerGenerator(Protocol):
    """Generates answer text from labeled passages.

    ``context`` is a list of ``(1-based_index, verbatim_passage)`` tuples,
    ready to render as ``[S1] ... [S2] ...``. The implementation must keep
    every claim within the passages and cite the markers it uses.
    """

    name: str

    def generate(self, question: str, context: list[tuple[int, str]]) -> str:
        """Return the answer text with ``[S#]`` citations."""
        ...


class ExtractiveGenerator:
    """Deterministic, offline generator that quotes retrieved passages.

    It cannot invent facts: every sentence is lifted verbatim from a passage
    and tagged with its source marker, then the answer states which source it
    came from.
    """

    name = "extractive"

    def generate(self, question: str, context: list[tuple[int, str]]) -> str:
        if not context:
            return "No supporting passages were retrieved, so no answer can be given."
        lines: list[str] = []
        # Quote the strongest passages.
        for idx, passage in context[:3]:
            trimmed = _squeeze(passage)
            lines.append(f"[S{idx}] {trimmed}")
        lines.append("")
        source_list = ", ".join(f"[S{idx}]" for idx, _ in context[:3])
        lines.append(
            f"The above excerpts (from {source_list}) are the retrieved support for the question."
        )
        return "\n".join(lines)


def render_context(
    sources: tuple[RetrievedSource, ...], config: RagConfig
) -> list[tuple[int, str]]:
    """Build ``(index, passage)`` prompts from retrieved sources."""
    context: list[tuple[int, str]] = []
    for idx, source in enumerate(sources, start=1):
        passage = source.passage
        if len(passage) > config.max_source_chars:
            passage = passage[: config.max_source_chars] + "…"
        context.append((idx, passage))
    return context


def verify_grounding(
    answer: str,
    n_sources: int,
    *,
    fraction: float,
) -> tuple[bool, tuple[str, ...]]:
    """Assess whether *answer* is properly grounded in the given sources."""
    notes: list[str] = []
    if not n_sources:
        return False, ("no sources provided",)
    markers = _MARKER_RE.findall(answer)
    if not markers:
        return False, ("answer cites no sources",)
    used = {int(m[1:]) for m in markers}
    out_of_range = sorted(i for i in used if i <= 0 or i > n_sources)
    if out_of_range:
        notes.append(f"markers out of range: {out_of_range}")

    sentences = [s for s in _SENTENCE_SPLIT.split(answer) if s.strip()]
    attributed = sum(1 for s in sentences if _MARKER_RE.search(s))
    if sentences and attributed / len(sentences) < fraction:
        notes.append(f"only {attributed}/{len(sentences)} sentences carry a citation")

    if not notes:
        return True, ("all claims are cited",)
    return False, tuple(notes)


def generate_answer(
    question: str,
    sources: tuple[RetrievedSource, ...],
    *,
    generator: AnswerGenerator,
    config: RagConfig | None = None,
) -> tuple[str, tuple[str, ...], bool]:
    """Run the generator and return ``(answer, notes, grounded)``."""
    config = config or DEFAULT_RAG_CONFIG
    context = render_context(sources, config)
    answer = generator.generate(question, context)
    grounded, notes = verify_grounding(answer, len(sources), fraction=config.min_grounded_fraction)
    return answer, notes, grounded


def _squeeze(text: str) -> str:
    return " ".join(text.split())


__all__ = [
    "AnswerGenerator",
    "ExtractiveGenerator",
    "generate_answer",
    "render_context",
    "verify_grounding",
]
