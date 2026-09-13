"""ORM models for the knowledge base.

Importing this package registers every table on ``Base.metadata`` (used by
Alembic autogenerate and by tests that create/drop tables).
"""

from __future__ import annotations

from knowledge_base.database.base import Base
from knowledge_base.database.models import (
    books,
    embeddings,
    hadith,
    metadata,
    normalization,
    ocr,
    quran,
    search,
    sources,
    structure,
)

__all__ = [
    "Base",
    "books",
    "embeddings",
    "hadith",
    "metadata",
    "normalization",
    "ocr",
    "quran",
    "search",
    "sources",
    "structure",
]