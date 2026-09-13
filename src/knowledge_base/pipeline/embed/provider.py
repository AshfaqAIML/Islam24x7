"""Embedding providers.

The embed processor talks to a thin :class:`EmbeddingProvider` interface so no
single AI provider is hard-coded into the architecture. Providers are looked
up by name — the built-in local ``dummy`` backend plus any
``pkg.module:ClassName`` path — see :func:`build_provider`.

Providers are piecewise replaceable:

- ``dummy`` — deterministic, dependency-free hashing backend used by the test
  suite and for local development. Vectors are unit-normed feature counts over
  character n-grams, so similar text scores a higher cosine similarity.
- ``pkg.module:ClassName`` — your own provider; the class must expose ``name``,
  ``version``, ``dimensions`` and an ``embed(texts)`` method returning one
  vector (``list[float]``, ``len == dimensions``) per input text.

Retry and rate-limit resilience live here too (:func:`embed_with_retry` and
:class:`RateLimiter`) so every provider gets the same treatment.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import time
from collections import deque
from collections.abc import Sequence
from typing import Protocol, cast

from knowledge_base.logging import logger
from knowledge_base.pipeline.embed.config import EmbedConfig


class EmbeddingProviderUnavailable(RuntimeError):
    """Raised when the requested provider cannot be built on this machine."""


class EmbeddingError(RuntimeError):
    """Transient provider failure (network hiccup, bad batch, ...).

    Retryable: :func:`embed_with_retry` backs off and retries up to
    ``max_retries`` before surfacing this error to the pipeline.
    """


class RateLimitedError(EmbeddingError):
    """The provider asked the client to wait (HTTP 429 or equivalent)."""


class EmbeddingProvider(Protocol):
    """Interface implemented by every embedding backend."""

    name: str
    version: str
    dimensions: int
    source_model: str | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text; ``len(vector) == dimensions``."""
        ...  # pragma: no cover


def build_provider(name: str, config: EmbedConfig) -> EmbeddingProvider:
    """Return a provider for ``name``; ``name`` may be a fully qualified class
    path for custom providers (``pkg.module:ClassName``)."""
    if name == "dummy":
        return DummyEmbeddingProvider(dimensions=config.dimensions)
    if name == "sentence-transformers":
        return SentenceTransformerProvider()
    if ":" in name:
        module_name, _, class_name = name.partition(":")
        return _load_custom(module_name, class_name)
    raise EmbeddingProviderUnavailable(
        f"Unknown embedding provider {name!r}. Choose 'dummy', 'sentence-transformers', "
        f"or a 'pkg.module:ClassName' path."
    )


def _load_custom(module_name: str, class_name: str) -> EmbeddingProvider:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise EmbeddingProviderUnavailable(
            f"Cannot import provider module {module_name!r}: {exc}"
        ) from exc
    provider_class = getattr(module, class_name, None)
    if not isinstance(provider_class, type):
        raise EmbeddingProviderUnavailable(f"{module_name}.{class_name} is not a class")
    return cast(EmbeddingProvider, provider_class())


class DummyEmbeddingProvider:
    """Deterministic local backend for tests and offline development.

    Each vector is a unit-normed signed count of character n-grams hashed
    into ``dimensions`` buckets. Identical input produces an identical
    vector, and overlapping text shares buckets (higher cosine similarity).
    """

    name = "dummy"
    source_model: str | None = None

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions
        self.version = "0.1.0"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_buckets(text, self.dimensions) for text in texts]

    def __repr__(self) -> str:
        return f"<DummyEmbeddingProvider dims={self.dimensions} v{self.version}>"


class SentenceTransformerProvider:
    """A local multilingual embedding backend via ``sentence-transformers``.

    Uses a deterministic ONNX-free local model (``paraphrase-multilingual-mpnet
    -base-v2``, 768 dims, 50+ languages) so no network or API key is needed
    after the initial model download. Vectors are L2-normalised, matching how
    the pgvector cosine search expects them.

    The model tensors are loaded once per process and reused across batches.
    """

    name = "sentence-transformers"
    source_model: str | None = "paraphrase-multilingual-mpnet-base-v2"
    _model = None  # process-wide shared SentenceTransformer instance

    def __init__(self, model_name: str | None = None) -> None:
        if model_name:
            self.source_model = model_name
        self._resolve()
        self.version = self._resolve_version()
        self.dimensions = self._model.get_sentence_embedding_dimension()  # type: ignore[attr-defined]

    def _resolve(self) -> None:
        if SentenceTransformerProvider._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderUnavailable(
                "sentence-transformers is not installed. "
                "Run `uv add sentence-transformers` (see docs/ocr-setup.md)."
            ) from exc
        try:
            SentenceTransformerProvider._model = SentenceTransformer(
                self.source_model,
                device=_device(),
            )
        except Exception as exc:
            raise EmbeddingProviderUnavailable(
                f"sentence-transformers could not load model {self.source_model!r}: {exc}"
            ) from exc

    @staticmethod
    def _resolve_version() -> str:
        try:
            import importlib.metadata

            return importlib.metadata.version("sentence-transformers")
        except Exception:
            return "unknown"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = SentenceTransformerProvider._model
        assert model is not None
        encoded = model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [row.tolist() for row in encoded]

    def __repr__(self) -> str:
        return (
            f"<SentenceTransformerProvider model={self.source_model} "
            f"dims={self.dimensions} v{self.version}>"
        )


def _device() -> str:
    """Use CUDA when available, otherwise CPU (deterministic local runs)."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _char_ngrams(text: str, width: int = 3) -> list[str]:
    folded = text.casefold()
    if len(folded) < width:
        return [folded] if folded else []
    return [folded[i : i + width] for i in range(len(folded) - width + 1)]


def _hash_buckets(text: str, dims: int) -> list[float]:
    if dims < 1:
        raise ValueError("embedding dimensions must be >= 1")
    feature = [0.0] * dims
    for gram in _char_ngrams(text):
        digest = hashlib.sha256(gram.encode("utf-8", errors="ignore")).digest()
        bucket = int.from_bytes(digest[:8], "big") % dims
        polarity = 1.0 if digest[8] & 1 == 0 else -1.0
        feature[bucket] += polarity
    norm = math.sqrt(sum(v * v for v in feature))
    if norm == 0.0:
        return [1.0] + [0.0] * (dims - 1)
    return [v / norm for v in feature]


class RateLimiter:
    """Client-side throttle so configured provider rate limits are respected.

    ``calls_per_minute > 0`` enforces a sliding-window quota; a
    ``min_interval`` (auto-derived from the quota when zero) keeps consecutive
    calls spaced out.
    """

    def __init__(self, *, calls_per_minute: int = 0, min_interval: float = 0.0) -> None:
        self.calls_per_minute = max(0, int(calls_per_minute))
        self.min_interval = max(0.0, min_interval)
        if self.calls_per_minute and not self.min_interval:
            self.min_interval = 60.0 / self.calls_per_minute
        self._window: deque[float] = deque()
        self._last: float | None = None

    def wait(self) -> None:
        """Block until a provider call is allowed under the configured limits."""
        now = time.monotonic()
        if self.min_interval and self._last is not None:
            gap = self.min_interval - (now - self._last)
            if gap > 0:
                time.sleep(gap)
                now = time.monotonic()
        if self.calls_per_minute:
            cutoff = now - 60.0
            while self._window and self._window[0] <= cutoff:
                self._window.popleft()
            if len(self._window) >= self.calls_per_minute:
                wait = 60.0 - (now - self._window[0])
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
        self._window.append(now)
        self._last = now


def embed_with_retry(
    provider: EmbeddingProvider,
    texts: Sequence[str],
    *,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
) -> list[list[float]]:
    """Embed ``texts``, backing off on rate limits and transient errors.

    Retries exponentially (``backoff_seconds * 2 ** attempt``) up to
    ``max_retries``; exhausting them raises :class:`EmbeddingError`.
    """
    attempt = 0
    while True:
        try:
            vectors = provider.embed(texts)
        except EmbeddingError as exc:
            reason = "rate-limited" if isinstance(exc, RateLimitedError) else "failed"
            if attempt >= max_retries:
                raise EmbeddingError(
                    f"provider {provider.name} {reason} after {attempt + 1} attempts: {exc}"
                ) from exc
            delay = backoff_seconds * (2**attempt)
            logger.warning(
                "embed provider={} {} attempt={}/{} retrying in {}s",
                provider.name,
                reason,
                attempt + 1,
                max_retries,
                delay,
            )
            time.sleep(delay)
            attempt += 1
        else:
            return vectors


__all__ = [
    "DummyEmbeddingProvider",
    "EmbeddingError",
    "EmbeddingProvider",
    "EmbeddingProviderUnavailable",
    "RateLimitedError",
    "RateLimiter",
    "SentenceTransformerProvider",
    "build_provider",
    "embed_with_retry",
]
