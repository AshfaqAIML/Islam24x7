"""FastAPI application for the knowledge base."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from knowledge_base.api.schemas import (
    AskRequest,
    AskResponse,
    SearchRequest,
    SearchResponse,
    SourceResponse,
    StatusResponse,
)
from knowledge_base.config import get_settings
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.embeddings import Embedding
from knowledge_base.database.models.hadith import Hadith
from knowledge_base.database.models.quran import Ayah, Translation
from knowledge_base.database.models.search import SearchDocument
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.database.models.structure import ContentChunk
from knowledge_base.database.session import create_app_engine
from knowledge_base.rag.service import RagService


def create_app() -> FastAPI:
    """Build the FastAPI application wired to configured settings."""
    settings = get_settings()
    engine = create_app_engine(settings.database_url)
    # FastAPI canonical dependency-injection for a request-scoped session.
    factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)

    def _session() -> Iterator[Session]:
        """Yield a short-lived read session for one request."""
        with factory() as session:
            yield session

    app = FastAPI(
        title="Islam24x7 Knowledge Base API",
        version="0.1.0",
        description=(
            "Local retrieval and grounded question-answering over the Islamic knowledge base."
        ),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status", response_model=StatusResponse)
    def status(session: Session = Depends(_session)) -> StatusResponse:  # noqa: B008
        quran_translations = session.scalar(select(func.count()).select_from(Translation)) or 0
        counts = {
            "sources": session.scalar(select(func.count()).select_from(SourceFile)) or 0,
            "books": session.scalar(select(func.count()).select_from(Book)) or 0,
            "chunks": session.scalar(select(func.count()).select_from(ContentChunk)) or 0,
            "embeddings": session.scalar(select(func.count()).select_from(Embedding)) or 0,
            "search_documents": session.scalar(select(func.count()).select_from(SearchDocument))
            or 0,
            "quran_ayahs": session.scalar(select(func.count()).select_from(Ayah)) or 0,
            "quran_translations": quran_translations,
            "hadith": session.scalar(select(func.count()).select_from(Hadith)) or 0,
        }
        return StatusResponse(**counts)

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest, session: Session = Depends(_session)) -> AskResponse:  # noqa: B008
        svc = RagService(settings=get_settings())
        ans = svc.answer(
            session,
            req.question,
            language=req.language,
            category=req.category,
            source=req.source,
            author=req.author,
            k=req.k,
        )
        return AskResponse(
            question=ans.question,
            answer=ans.answer,
            grounded=ans.grounded,
            ground_notes=list(ans.ground_notes or []),
            sources=[
                SourceResponse(
                    chunk_id=s.chunk_id or "",
                    reference=s.reference,
                    passage=s.passage,
                    score=s.score,
                    fts_score=s.fts_score,
                    vector_score=s.vector_score,
                    retrievers=list(s.retrievers or ()),
                )
                for s in ans.sources
            ],
            generator=ans.generator,
            model=ans.model,
            retrieval_ms=int(ans.retrieval_ms or 0),
            generation_ms=int(ans.generation_ms or 0),
        )

    @app.post("/search", response_model=SearchResponse)
    def search(req: SearchRequest, session: Session = Depends(_session)) -> SearchResponse:  # noqa: B008
        from knowledge_base.search.engine import SearchParams, search

        params = SearchParams(
            query=req.query,
            domains=("content", "book", "chapter", "section", "quran", "hadith"),
            all_terms=req.all_terms,
            language=req.language,
            category=req.category,
            source=req.source,
            author=req.author,
            limit=req.limit,
        )
        hits = search(session, params)
        return SearchResponse(query=req.query, hits=[asdict(h) for h in hits])

    @app.get("/ask")
    def ask_get_unavailable() -> None:
        raise HTTPException(status_code=405, detail="Use POST /ask with a JSON body")

    return app
