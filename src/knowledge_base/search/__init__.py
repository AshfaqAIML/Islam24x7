"""Search API.

Hybrid retrieval over validated content: PostgreSQL full-text candidates
combined with pgvector similarity, ranked and resolved back to
citations/pages. By default restricted to published/verified content.
"""