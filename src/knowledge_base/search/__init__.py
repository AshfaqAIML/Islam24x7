"""Full-text search: query parsing, indexing-backed engine, and hit model."""

from __future__ import annotations

from knowledge_base.search.engine import SearchParams, search
from knowledge_base.search.hits import SearchHit
from knowledge_base.search.queries import build_websearch, parse_query, sniff_language

__all__ = [
    "SearchHit",
    "SearchParams",
    "build_websearch",
    "parse_query",
    "search",
    "sniff_language",
]