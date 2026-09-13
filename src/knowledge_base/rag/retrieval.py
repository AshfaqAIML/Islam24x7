"""Retrieval: turn a question into grounded, provenance-rich passages.

Uses the existing hybrid search (keyword + semantic) against the content
chunks, then **rehydrates** each hit's database row to build the citation.
Citations are therefore never invented: they are produced by
``citation_from_chunk`` on the loaded ``ContentChunk`` record.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.citations import Citation, citation_from_chunk
from knowledge_base.database.models.structure import ContentChunk
from knowledge_base.rag.config import DEFAULT_RAG_CONFIG, RagConfig
from knowledge_base.rag.models import RetrievalQuery, RetrievalResult, RetrievedSource


class RetrievalBackend(Protocol):
    """Pluggable search backend; the default wraps hybrid search."""

    def search(self, session: Session, query: RetrievalQuery, *, limit: int) -> list[Any]:
        """Return raw hits (anything with ``chunk_id``, ``score``, ``text``)."""
        ...


@dataclass(frozen=True)
class RetrieveResult:
    """Backend-agnostic hit view (used by tests with stub backends)."""

    chunk_id: str
    text: str
    score: float
    fts_score: float | None = None
    vector_score: float | None = None
    retrievers: tuple[str, ...] = field(default_factory=tuple)


def retrieve(
    session: Session,
    query: RetrievalQuery,
    *,
    config: RagConfig | None = None,
    backend: RetrievalBackend | None = None,
    provider: Any = None,
    model_name: str,
    model_version: str | None = None,
) -> RetrievalResult:
    """Retrieve grounded passages for *query*.

    ``provider``/``model_name``/``model_version`` enable the semantic path of
    the default hybrid backend. Pass a custom ``backend`` to test retrieval
    logic without a search index.
    """
    config = config or DEFAULT_RAG_CONFIG
    backend = backend or _HybridBackend(
        provider=provider, model_name=model_name, model_version=model_version
    )
    limit = query.k or config.top_k
    started = time.perf_counter()
    raw = backend.search(session, query, limit=limit)
    elapsed_ms = _ms_since(started)

    sources: list[RetrievedSource] = []
    for hit in raw:
        source = _to_source(session, hit)
        if source is None:
            continue
        if query.min_score is not None and source.score < query.min_score:
            continue
        if config.min_score is not None and source.score < config.min_score:
            continue
        sources.append(source)

    sources.sort(key=lambda s: s.score, reverse=True)
    sources = sources[:limit]
    used_fts = any("fts" in s.retrievers for s in sources)
    used_vector = any("vector" in s.retrievers for s in sources)
    note = None
    if provider is None:
        note = "vector search disabled (no embedding provider)"
    elif not used_vector:
        note = "vector path returned no hits; keyword only"
    if not sources:
        note = "no passages retrieved"

    return RetrievalResult(
        query=query,
        sources=tuple(sources),
        used_fts=used_fts,
        used_vector=used_vector,
        note=note,
        elapsed_ms=elapsed_ms,
    )


def _to_source(session: Session, hit: Any) -> RetrievedSource | None:
    """Build a ``RetrievedSource`` from a backend hit, rehydrating the chunk."""
    chunk_id = getattr(hit, "chunk_id", None)
    text = getattr(hit, "text", None) or getattr(hit, "matched_text", None)
    score = float(getattr(hit, "score", 0.0) or 0.0)
    if not text or not chunk_id:
        return None

    citation = _citation_for(session, chunk_id, hit)
    return RetrievedSource(
        citation=citation,
        passage=text,
        score=score,
        reference=citation.reference(),
        chunk_id=chunk_id,
        fts_score=getattr(hit, "fts_score", None),
        vector_score=getattr(hit, "vector_score", None),
        retrievers=tuple(getattr(hit, "retrievers", ())),
    )


def _citation_for(session: Session, chunk_id: str, hit: Any) -> Citation:
    """Prefer a DB-loaded citation; fall back to a minimal DB-derived one."""
    chunk = session.execute(
        select(ContentChunk).where(ContentChunk.chunk_id == chunk_id).limit(1)
    ).scalar_one_or_none()
    if chunk is not None:
        return citation_from_chunk(chunk)
    # Fall back to fields the search layer read off the DB directly.
    return Citation(
        source_type="book",
        book_id=getattr(hit, "book_id", None),
        book_title=getattr(hit, "book", None),
        chapter_id=getattr(hit, "chapter_id", None),
        chapter_title=getattr(hit, "chapter", None),
        section_id=getattr(hit, "section_id", None),
        section_title=getattr(hit, "section", None),
        page=getattr(hit, "page", None),
        chunk_id=chunk_id,
        source_file_id=getattr(hit, "source_id", None),
    )


class _HybridBackend:
    """Default backend: fuses keyword + semantic search via hybrid_search."""

    def __init__(
        self,
        *,
        provider: Any,
        model_name: str,
        model_version: str | None,
        weight_fts: float = 0.5,
        weight_vector: float = 0.5,
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._model_version = model_version
        self._weight_fts = weight_fts
        self._weight_vector = weight_vector

    def search(self, session: Session, query: RetrievalQuery, *, limit: int) -> list[Any]:
        from knowledge_base.search.hybrid import hybrid_search

        return hybrid_search(
            session,
            query.question,
            provider=self._provider,
            model_name=self._model_name,
            model_version=self._model_version,
            weight_fts=self._weight_fts,
            weight_vector=self._weight_vector,
            limit=limit,
            category=query.category,
            source=query.source,
            language=query.language,
            source_type=query.source_type,
            author=query.author,
            min_score=query.min_score,
        )


def _ms_since(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


__all__ = ["RetrievalBackend", "RetrieveResult", "retrieve"]
