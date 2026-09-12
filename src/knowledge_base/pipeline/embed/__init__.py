"""Embedding generation for vector search.

Produces embeddings from chunk text (embedding models tracked by name,
provider, dims, version) for storage in a pgvector column. Never uses the
source-replacing variant and never invents content.
"""