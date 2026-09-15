"""Request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """A question to answer with source-grounded retrieval."""

    question: str = Field(..., min_length=1, max_length=2000)
    language: str | None = Field(default=None, pattern="^(ar|ur|en)$")
    category: str | None = None
    source: str | None = None
    author: str | None = None
    k: int | None = Field(default=None, ge=1, le=50)


class SourceResponse(BaseModel):
    """One retrieved passage with its provenance."""

    chunk_id: str
    reference: str
    passage: str
    score: float
    fts_score: float | None = None
    vector_score: float | None = None
    retrievers: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    """The grounded answer plus its support and trace."""

    question: str
    answer: str
    grounded: bool
    ground_notes: list[str] = Field(default_factory=list)
    sources: list[SourceResponse] = Field(default_factory=list)
    generator: str
    model: str | None = None
    retrieval_ms: int = 0
    generation_ms: int = 0


class SearchRequest(BaseModel):
    """Full-text search parameters."""

    query: str = Field(..., min_length=1, max_length=500)
    domains: list[str] | None = Field(default=None, max_length=16)
    all_terms: bool = False
    language: str | None = Field(default=None, pattern="^(ar|ur|en)$")
    category: str | None = None
    source: str | None = None
    author: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SearchResponse(BaseModel):
    """Search hits with provenance and snippets."""

    query: str
    hits: list[dict[str, object]] = Field(default_factory=list)


class StatusResponse(BaseModel):
    """Knowledge-base dashboard numbers."""

    sources: int = 0
    books: int = 0
    chunks: int = 0
    embeddings: int = 0
    search_documents: int = 0
    quran_ayahs: int = 0
    quran_translations: int = 0
    hadith: int = 0
