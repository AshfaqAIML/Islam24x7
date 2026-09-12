"""Shared pytest fixtures for database-backed tests."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from knowledge_base.database import reset_schema
from knowledge_base.database.base import Base
from knowledge_base.database.session import create_app_engine

_TEST_URL = os.environ.get(
    "KB_TEST_DATABASE_URL",
    "postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base_test",
)


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Engine bound to the test database; schema reset once per session."""
    if "sqlite" in _TEST_URL:
        pytest.skip("PostgreSQL only (pgvector/tsvector/enums)")
    engine = create_app_engine(_TEST_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - infra-dependent
        engine.dispose()
        pytest.skip(f"test database unreachable: {exc}")
    reset_schema(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine: Engine) -> Iterator[Session]:
    """Fresh transaction for each test; rolled back and truncated afterwards."""
    factory = sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    session = factory()
    session.begin()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        tables = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
        with db_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} CASCADE"))


__all__ = ["db", "db_engine"]