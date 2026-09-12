"""SQLAlchemy declarative base and shared column mixins.

All tables inherit from :class:`Base` and share a stable ``uuid`` primary key
and server-managed timestamps.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all knowledge-base tables."""


class TimestampMixin:
    """Server-managed ``created_at`` / ``updated_at`` columns (UTC-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def new_uuid() -> uuid.UUID:
    """Return a fresh UUID v4 used as the stable primary key."""
    return uuid.uuid4()


class UUIDPrimaryKeyMixin:
    """Stable, application-generated UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=new_uuid,
    )


def make_enum(python_enum: type[Any]) -> Any:
    """Build a native PostgreSQL ENUM type from a Python enum."""
    from sqlalchemy import Enum

    return Enum(
        python_enum,
        name=f"kb_{python_enum.__name__.lower()}",
        values_callable=lambda e: [m.value for m in e],
        native_enum=True,
    )