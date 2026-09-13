"""Tuning knobs for the RAG pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RagConfig:
    """Configuration for retrieval + generation.

    All defaults are conservative for religious content: verbatim passages
    (``max_source_chars`` cap only for the prompt, never the stored text),
    hybrid retrieval weights that keep keyword search always available, and a
    strict grounding threshold before an answer is marked ``grounded``.
    """

    #: How many passages to feed the generator (retrieval top-k).
    top_k: int = 8
    #: Drop passes below this weighted score (None = no floor).
    min_score: float | None = None
    #: Relative weight of the keyword path (0 disables it).
    weight_fts: float = 0.5
    #: Relative weight of the semantic path (0 disables it).
    weight_vector: float = 0.5
    #: Maximum characters of one passage sent to the generator.
    max_source_chars: int = 2000
    #: Minimum fraction of answer sentences that must cite a source marker
    #: for the answer to count as ``grounded``.
    min_grounded_fraction: float = 0.6
    #: Marker prefix used in prompts, e.g. ``[S1]``.
    source_marker_prefix: str = "S"

    #: Generation provider (``extractive`` built in; custom via
    #: ``pkg.module:ClassName``).
    generator: str = "extractive"
    #: Optional generator model label surfaced in ``RagAnswer.model``.
    generator_model: str | None = None
    #: Generation temperature hint (only used by LLM generators).
    temperature: float = 0.2
    #: Max generated tokens (only used by LLM generators).
    max_tokens: int = 500
    system_prompt: str = field(
        default=(
            "Answer the question using ONLY the provided excerpts. Every "
            "claim must be supported by an excerpt; cite each excerpt with its "
            "[S#] marker. If the excerpts do not answer the question, say so."
        )
    )


DEFAULT_RAG_CONFIG = RagConfig()


__all__ = ["DEFAULT_RAG_CONFIG", "RagConfig"]
