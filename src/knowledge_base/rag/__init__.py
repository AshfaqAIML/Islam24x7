"""RAG module: source-grounded question answering over the knowledge base.

Contract — **everything the answer says must come from retrieved passages**:

* Retrieval produces :class:`RetrievedSource` objects that carry a database-
  derived :class:`~knowledge_base.citations.Citation` plus the verbatim passage
  text that was actually retrieved (never an LLM rewrite).
* Generation consumes **only** those passages and must cite them with
  ``[S1]``-style markers; ``verify_grounding`` rejects answers whose markers
  are out of range or that leave too many assertions unattributed.
* The built-in :class:`ExtractiveGenerator` is deterministic and offline —
  it composes an answer from the passages themselves, so it can never
  fabricate a fact. External LLM generators plug in behind the same protocol.

The module is future-looking for the W4 API: the same ``RagService`` methods
back a CLI ``ask`` command and an HTTP endpoint.
"""

from __future__ import annotations

from knowledge_base.rag.config import DEFAULT_RAG_CONFIG, RagConfig
from knowledge_base.rag.models import (
    RagAnswer,
    RetrievalQuery,
    RetrievalResult,
    RetrievedSource,
)
from knowledge_base.rag.retrieval import RetrieveResult, retrieve
from knowledge_base.rag.service import RagService

__all__ = [
    "DEFAULT_RAG_CONFIG",
    "RagAnswer",
    "RagConfig",
    "RagService",
    "RetrievedSource",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrieveResult",
    "retrieve",
]
