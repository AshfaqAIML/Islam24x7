"""Orchestration: turn one question into a grounded answer.

``RagService`` wires retrieval (hybrid search over content chunks with
database-derived citations) and generation (default extractive / pluggable
LLM) together, and degrades gracefully when the embedding provider or the
embedding model is unavailable: keyword-only retrieval still works.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from knowledge_base.config import Settings, get_settings
from knowledge_base.pipeline.embed.config import EmbedConfig
from knowledge_base.pipeline.embed.provider import (
    EmbeddingProviderUnavailable,
    build_provider,
)
from knowledge_base.rag.config import DEFAULT_RAG_CONFIG, RagConfig
from knowledge_base.rag.generation import AnswerGenerator, ExtractiveGenerator, generate_answer
from knowledge_base.rag.models import RagAnswer, RetrievalQuery, RetrievalResult
from knowledge_base.rag.retrieval import retrieve


class RagService:
    """Facade for the end-to-end question-answering flow."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        config: RagConfig | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.config = config or DEFAULT_RAG_CONFIG
        self.generator = generator or ExtractiveGenerator()

    def _provider(self) -> tuple[Any, str, str | None] | None:
        """(provider, model_name, model_version) or None when semantics unavailable."""
        try:
            provider = build_provider(
                self.settings.embedding_provider,
                EmbedConfig.from_settings(self.settings),
            )
        except EmbeddingProviderUnavailable:
            return None
        return (provider, self.settings.embedding_model, self.settings.embedding_model_version)

    def retrieve(
        self,
        session: Session,
        question: str,
        *,
        language: str | None = None,
        category: str | None = None,
        source: str | None = None,
        source_type: str | None = None,
        author: str | None = None,
        k: int | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        query = RetrievalQuery(
            question=question,
            language=language,
            category=category,
            source=source,
            source_type=source_type,
            author=author,
            k=k,
            min_score=min_score,
        )
        provider_bundle = self._provider()
        if provider_bundle is None:
            return retrieve(
                session,
                query,
                config=self.config,
                provider=None,
                model_name=self.settings.embedding_model,
            )
        provider, model_name, model_version = provider_bundle
        return retrieve(
            session,
            query,
            config=self.config,
            provider=provider,
            model_name=model_name,
            model_version=model_version,
        )

    def answer(
        self,
        session: Session,
        question: str,
        *,
        language: str | None = None,
        category: str | None = None,
        source: str | None = None,
        source_type: str | None = None,
        author: str | None = None,
        k: int | None = None,
    ) -> RagAnswer:
        """Answer *question* grounded on retrieved passages."""
        result = self.retrieve(
            session,
            question,
            language=language,
            category=category,
            source=source,
            source_type=source_type,
            author=author,
            k=k,
        )
        retrieval_ms = result.elapsed_ms
        gen_started = time.perf_counter()
        answer, notes, grounded = generate_answer(
            question, result.sources, generator=self.generator, config=self.config
        )
        generation_ms = int((time.perf_counter() - gen_started) * 1000)
        return RagAnswer(
            question=question,
            answer=answer,
            sources=result.sources,
            grounded=grounded,
            ground_notes=notes,
            generator=self.generator.name,
            model=self.config.generator_model,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
        )


__all__ = ["RagService"]
