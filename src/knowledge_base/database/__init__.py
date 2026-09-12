"""Database layer: SQLAlchemy models, sessions, and Alembic migrations.

Importing this package registers every ORM model on ``Base.metadata``.
Migrations live under ``src/knowledge_base/database/migrations/``.
"""

from __future__ import annotations

from knowledge_base.database.base import Base
from knowledge_base.database.models import (  # noqa: F401  (registers tables)
    books,
    embeddings,
    hadith,
    quran,
    search,
    sources,
    structure,
)
from knowledge_base.database.session import (
    create_app_engine,
    ensure_schema,
    is_postgres_url,
    make_session_factory,
    reset_schema,
    session_scope,
)

__all__ = [
    "Base",
    "create_app_engine",
    "ensure_schema",
    "is_postgres_url",
    "make_session_factory",
    "reset_schema",
    "session_scope",
]