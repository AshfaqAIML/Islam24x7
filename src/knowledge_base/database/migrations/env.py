"""Alembic migration environment.

Reads the database URL from ``KB_DATABASE_URL`` (settings) unless an explicit
``sqlalchemy.url`` is present, and uses the knowledge-base metadata so
``revision --autogenerate`` works out of the box.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from knowledge_base.config import get_settings
from knowledge_base.database.base import Base

# Importing the models package registers every table on Base.metadata.
import knowledge_base.database.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Allow env override with highest priority.
env_url = os.environ.get("KB_DATABASE_URL")
if env_url:
    config.set_main_option("sqlalchemy.url", env_url)

target_metadata = Base.metadata


def _effective_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    settings_url = get_settings().database_url
    if not settings_url:
        raise ValueError("KB_DATABASE_URL is not set and no sqlalchemy.url is configured")
    return settings_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB round-trip."""
    context.configure(
        url=_effective_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _effective_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()