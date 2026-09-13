"""Data contracts for retrieval and answers.

The central invariant is provenance: every ``RetrievedSource`` carries a
:class:`~knowledge_base.citations.Citation` that is built from database rows
(see ``knowledge_base.citations``), never assembled free-form. The citation's
``reference()`` is the human-readable string an answer may display.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from knowledge_base.citations import Citation


@dataclass(frozen=True)
class RetrievalQuery:
    """What the user asked and how retrieval should scope it."""

    question: str
    #: Optional language/hint to scope results (None = any language).
    language: str | None = None
    #: Categories keep same semantics as the search layer.
    category: str | None = None
    #: Source sha256 prefix to restrict to one source file.
    source: str | None = None
    source_type: str | None = None
    author: str | None = None
    #: Overrides ``RagConfig.top_k`` when set.
    k: int | None = None
    #: Overrides ``RagConfig.min_score`` when set.
    min_score: float | None = None


@dataclass(frozen=True)
class RetrievedSource:
    """One passage the generator may ground an answer on.

    ``passage`` is the verbatim text from the knowledge base. ``citation`` is
    database-derived; ``reference`` is its compact display form. ``score`` is
    the fused hybrid score; individual path scores are kept for transparency.
    """

    citation: Citation
    passage: str
    score: float
    reference: str
    chunk_id: str | None = None
    fts_score: float | None = None
    vector_score: float | None = None
    retrievers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RetrievalResult:
    """Outcome of one retrieval step."""

    query: RetrievalQuery
    sources: tuple[RetrievedSource, ...]
    used_fts: bool
    used_vector: bool
    note: str | None = None
    elapsed_ms: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.sources


@dataclass(frozen=True)
class RagAnswer:
    """Final grounded answer.

    ``answer`` text uses ``[S#]`` markers that index ``sources`` (1-based).
    ``grounded`` is True only when grounding verification passed.
    """

    question: str
    answer: str
    sources: tuple[RetrievedSource, ...]
    grounded: bool
    ground_notes: tuple[str, ...] = field(default_factory=tuple)
    generator: str = "extractive"
    model: str | None = None
    retrieval_ms: int | None = None
    generation_ms: int | None = None
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.answer


__all__ = ["RagAnswer", "RetrievedSource", "RetrievalQuery", "RetrievalResult"]
