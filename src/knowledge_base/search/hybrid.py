"""Hybrid retrieval over knowledge-base chunks.

Fuses keyword (full-text) retrieval with semantic (vector) retrieval:

    query
      -> keyword candidates  + semantic candidates     (candidate pool)
      -> normalized weighted score per chunk            (ranking)
      -> deduplicated, provenance-rich results

Both paths always run; end-to-end retrieval never depends on semantic search
alone.  Weights are configurable and each surviving hit reports the raw
keyword/semantic scores and which retrievers contributed to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge_base.database.models.sources import SourceFile
from knowledge_base.search.engine import SearchParams, search
from knowledge_base.search.vector import _QueryEmbedder, similar

_FTS_DOMAINS = ("content",)


@dataclass(frozen=True)
class HybridHit:
    """One hybrid result with full provenance and decision transparency."""

    chunk_id: str
    text: str
    score: float
    fts_score: float | None
    vector_score: float | None
    weight_fts: float
    weight_vector: float
    retrievers: tuple[str, ...]

    book: str | None = None
    book_id: str | None = None
    author: str | None = None
    category: str | None = None
    chapter: str | None = None
    chapter_id: str | None = None
    section: str | None = None
    section_id: str | None = None
    page: int | None = None
    source: str | None = None
    source_id: str | None = None
    source_type: str | None = None
    language: str | None = None
    content_id: str | None = None


def _pool_limit(limit: int) -> int:
    return max(limit * 3, 20)


def hybrid_search(
    session: Session,
    query: str,
    *,
    model_name: str,
    model_version: str | None = None,
    provider: _QueryEmbedder | None = None,
    weight_fts: float = 0.5,
    weight_vector: float = 0.5,
    limit: int = 20,
    category: str | None = None,
    source: str | None = None,
    language: str | None = None,
    source_type: str | None = None,
    author: str | None = None,
    min_score: float | None = None,
) -> list[HybridHit]:
    """Search with keyword and semantic retrieval combined.

    Parameters
    ----------
    provider:
        Embedding provider used to embed the query (as in ``embed`` /
        ``similar``).  When ``None`` the semantic path is skipped and only the
        keyword path is used — keyword search never depends on embeddings.
    weight_fts / weight_vector:
        Relative weight of each retrieval path.  Both default to 0.5; a path
        may be disabled with a weight of 0 (e.g. ``weight_vector=0`` for
        keyword-only, ``weight_fts=0`` for semantic-only).

    Returns
    -------
    list[HybridHit]
        Deduplicated chunk hits ranked by weighted score, source-rich.
    """
    if not query or not query.strip():
        return []

    pool: dict[str, dict[str, Any]] = {}
    max_rank = 0.0

    if weight_fts > 0:
        fts_hits = search(
            session,
            SearchParams(
                query=query,
                domains=_FTS_DOMAINS,
                language=language or None,
                category=category,
                source=source,
                author=author,
                limit=_pool_limit(limit),
            ),
        )
        if source_type:
            ids = {h.source_file_id for h in fts_hits if h.source_file_id}
            if ids:
                fmts = session.execute(
                    select(SourceFile.id, SourceFile.format).where(
                        SourceFile.id.in_(ids)
                    )
                ).all()
                keep = {row[0] for row in fmts if row[1].value == source_type}
                fts_hits = [h for h in fts_hits if h.source_file_id in keep]

        for khit in fts_hits:
            if not khit.chunk_id:
                continue
            entry = pool.setdefault(khit.chunk_id, _entry())
            if entry["text"] is None:
                entry["text"] = khit.matched_text
            _fill_search(entry, khit)
            entry["fts_score"] = max(entry["fts_score"] or 0.0, khit.rank or 0.0)
            entry["retrievers"].add("fts")
            max_rank = max(max_rank, khit.rank or 0.0)
            entry["content_id"] = khit.chunk_id

    if weight_vector > 0 and provider is not None:
        try:
            vec_hits = similar(
                session,
                query,
                provider,
                model_name=model_name,
                model_version=model_version,
                limit=_pool_limit(limit),
                category=category,
                source=source,
                language=language,
                source_type=source_type,
                author=author,
            )
        except ValueError:
            vec_hits = []
        for vhit in vec_hits:
            entry = pool.setdefault(vhit.chunk_id, _entry())
            if entry["text"] is None:
                entry["text"] = vhit.text
            _fill_vector(entry, vhit)
            entry["vector_score"] = max(entry["vector_score"] or 0.0, vhit.score)
            entry["retrievers"].add("vector")
            entry["content_id"] = vhit.content_id

    if not pool:
        return []

    results: list[HybridHit] = []
    for chunk_id, e in pool.items():
        rank = (e["fts_score"] or 0.0) / max_rank if max_rank > 0 else 0.0
        score = weight_fts * rank + weight_vector * (e["vector_score"] or 0.0)
        if min_score is not None and score < min_score:
            continue
        results.append(
            HybridHit(
                chunk_id=chunk_id,
                text=e["text"] or "",
                score=score,
                fts_score=e["fts_score"],
                vector_score=e["vector_score"],
                weight_fts=weight_fts,
                weight_vector=weight_vector,
                retrievers=tuple(sorted(e["retrievers"])),
                book=e["book"],
                book_id=e["book_id"],
                author=e["author"],
                category=e["category"],
                chapter=e["chapter"],
                chapter_id=e["chapter_id"],
                section=e["section"],
                section_id=e["section_id"],
                page=e["page"],
                source=e["source"],
                source_id=e["source_id"],
                source_type=e["source_type"],
                language=e["language"],
                content_id=e["content_id"],
            )
        )

    results.sort(key=lambda h: h.score, reverse=True)
    return results[:limit]


def _entry() -> dict[str, Any]:
    return {
        "text": None,
        "fts_score": None,
        "vector_score": None,
        "retrievers": set(),
        "book": None,
        "book_id": None,
        "author": None,
        "category": None,
        "chapter": None,
        "chapter_id": None,
        "section": None,
        "section_id": None,
        "page": None,
        "source": None,
        "source_id": None,
        "source_type": None,
        "language": None,
        "content_id": None,
    }


def _fill_search(entry: dict[str, Any], hit: Any) -> None:
    """Fill entry fields from a keyword ``SearchHit``."""
    entry["book"] = entry["book"] or hit.book
    entry["book_id"] = entry["book_id"] or hit.book_id
    entry["author"] = entry["author"] or hit.author
    entry["category"] = entry["category"] or hit.category
    entry["chapter"] = entry["chapter"] or hit.chapter
    entry["chapter_id"] = entry["chapter_id"] or hit.chapter_id
    entry["section"] = entry["section"] or hit.section
    entry["section_id"] = entry["section_id"] or hit.section_id
    entry["page"] = entry["page"] if entry["page"] is not None else hit.page
    entry["source_id"] = entry["source_id"] or hit.source_file_id
    entry["language"] = entry["language"] or hit.language


def _fill_vector(entry: dict[str, Any], hit: Any) -> None:
    """Fill entry fields from a semantic ``VectorHit``."""
    entry["book"] = entry["book"] or hit.book
    entry["book_id"] = entry["book_id"] or hit.book_id
    entry["author"] = entry["author"] or hit.author
    entry["category"] = entry["category"] or hit.category
    entry["chapter"] = entry["chapter"] or hit.chapter
    entry["chapter_id"] = entry["chapter_id"] or hit.chapter_id
    entry["section"] = entry["section"] or hit.section
    entry["section_id"] = entry["section_id"] or hit.section_id
    entry["page"] = entry["page"] if entry["page"] is not None else hit.page
    entry["source"] = entry["source"] or hit.source
    entry["source_id"] = entry["source_id"] or hit.source_id
    entry["source_type"] = entry["source_type"] or hit.source_type
    entry["language"] = entry["language"] or hit.language


__all__ = ["HybridHit", "hybrid_search"]