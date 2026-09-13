"""Full-text search indexing.

Builds PostgreSQL ``tsvector`` documents from chunked, normalized content with
language-aware text search configurations (Arabic, Urdu, English) and GIN
indexes.
"""

from knowledge_base.pipeline.index.index import IndexResult, index_all, index_book

__all__ = ["IndexResult", "index_all", "index_book"]