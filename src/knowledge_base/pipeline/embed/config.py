"""Embedding pipeline configuration.

Kept provider-agnostic: the processor relies only on ``provider_name``,
``model_name``/``model_version``/``dimensions`` (the identity of the model a
batch was produced with) and the resilience knobs below. Anything
provider-specific stays inside the backend implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowledge_base.config import Settings

# Physical width of the pgvector column (see ``embeddings.vector``). Providers
# with different dimensions need a schema migration before they can be used.
EMBEDDING_DIMENSIONS = 768


@dataclass(frozen=True)
class EmbedConfig:
    """Tunables for embedding generation, retries, and rate limiting."""

    provider_name: str = "dummy"
    """Backend name: ``dummy`` (tests/dev) or a ``pkg.module:ClassName`` path."""

    model_name: str = "kb-dummy"
    """Name under which vectors are tagged (see ``embedding_models.name``)."""

    model_version: str = "0.1.0"
    """Provider/model version; a bump forces a full re-embed for the new model."""

    dimensions: int = EMBEDDING_DIMENSIONS
    """Expected vector length for this model — must match the configured model
    and the physical pgvector column for storage."""

    batch_size: int = 64
    """Number of texts sent to the provider per call."""

    max_retries: int = 3
    """Times a failed/rate-limited provider call is retried before failing."""

    backoff_seconds: float = 1.0
    """Base exponential backoff between retries (``b * 2 ** attempt``)."""

    calls_per_minute: int = 0
    """Client-side quota (0 = unlimited); spaces out provider calls."""

    @classmethod
    def from_settings(cls, settings: Settings) -> EmbedConfig:
        """Build a config from the app ``Settings`` (env/``.env`` driven)."""
        return cls(
            provider_name=settings.embedding_provider,
            model_name=settings.embedding_model,
            model_version=settings.embedding_model_version,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
            max_retries=settings.embedding_max_retries,
            backoff_seconds=settings.embedding_backoff_seconds,
            calls_per_minute=settings.embedding_calls_per_minute,
        )


DEFAULT_EMBED_CONFIG = EmbedConfig()

__all__ = ["DEFAULT_EMBED_CONFIG", "EMBEDDING_DIMENSIONS", "EmbedConfig"]