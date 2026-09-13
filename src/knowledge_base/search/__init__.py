"""Search: full-text, semantic (vector), and hybrid retrieval.

The hybrid engine fuses keyword and semantic retrieval into one weighted,
deduplicated, provenance-rich result set.
"""

from __future__ import annotations

from knowledge_base.search.engine import SearchParams, search
from knowledge_base.search.hits import SearchHit
from knowledge_base.search.hybrid import HybridHit, hybrid_search
from knowledge_base.search.queries import build_websearch, parse_query, sniff_language
from knowledge_base.search.vector import VectorHit, similar

__all__ = [
    "HybridHit",
    "SearchHit",
    "SearchParams",
    "VectorHit",
    "build_websearch",
    "hybrid_search",
    "parse_query",
    "search",
    "similar",
    "sniff_language",
]