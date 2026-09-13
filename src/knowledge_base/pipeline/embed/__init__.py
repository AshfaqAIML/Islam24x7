"""Embedding generation for vector search.

Produces embeddings from chunk text (embedding models tracked by name,
provider, dims, version) for storage in a pgvector column. Never uses the
source-replacing variant and never invents content. The provider is
replaceable (see :mod:`knowledge_base.pipeline.embed.provider`).
"""

from knowledge_base.pipeline.embed.config import DEFAULT_EMBED_CONFIG, EmbedConfig
from knowledge_base.pipeline.embed.processor import EmbedResult, embed_all, embed_book
from knowledge_base.pipeline.embed.provider import (
    DummyEmbeddingProvider,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingProviderUnavailable,
    RateLimitedError,
    RateLimiter,
    build_provider,
    embed_with_retry,
)

__all__ = [
    "DEFAULT_EMBED_CONFIG",
    "DummyEmbeddingProvider",
    "EmbedConfig",
    "EmbedResult",
    "EmbeddingError",
    "EmbeddingProvider",
    "EmbeddingProviderUnavailable",
    "RateLimitedError",
    "RateLimiter",
    "build_provider",
    "embed_all",
    "embed_book",
    "embed_with_retry",
]