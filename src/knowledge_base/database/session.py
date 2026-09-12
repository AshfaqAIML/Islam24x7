"""Database engine, session factory, and connection helpers.

The default URL comes from ``KB_DATABASE_URL`` (see ``config.Settings``).
The test helper ``create_test_engine`` / ``session_scope`` support both the
live PostgreSQL and lightweight test setups.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from knowledge_base.config import get_settings
from knowledge_base.database.base import Base

# Default pool sizes tuned for a single-user pipeline running batches.
_DEFAULT_ENGINE_KWARGS: dict[str, Any] = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,
}


def build_url(url: str | None = None) -> str:
    """Return a usable database URL, falling back to configured settings."""
    if url:
        return url
    configured = get_settings().database_url
    if not configured:
        raise ValueError(
            "Database URL is not configured. Set KB_DATABASE_URL (see .env.example)."
        )
    return configured


def create_app_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine (defaults to the configured database URL)."""
    configured = build_url(url)
    merged = {**_DEFAULT_ENGINE_KWARGS, **kwargs}
    return create_engine(configured, **merged)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_schema(engine: Engine) -> None:
    """Create all tables and the pgvector extension if missing (used for tests/dev)."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)


def drop_schema(engine: Engine) -> None:
    """Drop all tables (used by tests for isolation)."""
    Base.metadata.drop_all(engine)


def reset_schema(engine: Engine) -> None:
    """Completely reset the public schema, recreating the vector extension.

    Used by tests to guarantee a pristine, reproducible schema.
    """
    engine.dispose()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def is_postgres_url(url: str) -> bool:
    """Return True if ``url`` points at PostgreSQL."""
    return make_url(url).get_backend_name() == "postgresql"