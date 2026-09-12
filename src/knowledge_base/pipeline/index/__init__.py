"""Full-text search indexing.

Builds PostgreSQL ``tsvector`` documents from chunked, normalized content with
language-aware text search configurations (Arabic, Urdu, English) and GIN
indexes.
"""