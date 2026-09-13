"""Search: full-text engine and semantic (vector) search over chunks."""

from __future__ import annotations

from knowledge_base.search.engine import SearchParams, search
from knowledge_base.search.hits import SearchHit
from knowledge_base.search.queries import build_websearch, parse_query, sniff_language
from knowledge_base.search.vector import VectorHit, similar

__all__ = [
    "SearchHit",
    "SearchParams",
    "VectorHit",
    "build_websearch",
    "parse_query",
    "search",
    "similar",
    "sniff_language",
]