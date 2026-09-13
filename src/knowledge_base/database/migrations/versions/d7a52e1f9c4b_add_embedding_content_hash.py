"""Add content-hash tracking to embeddings

Revision ID: d7a52e1f9c4b
Revises: c19d4e8f2b6a
Create Date: 2026-09-13

The embed pipeline must never regenerate vectors for unchanged content.
``embeddings.content_hash`` records the SHA-256 of the exact chunk text that
produced each vector, so a re-run can compare hashes and skip untouched
chunks (and regenerate only the ones whose text changed).
"""

import sqlalchemy as sa
from alembic import op

revision = "d7a52e1f9c4b"
down_revision = "c19d4e8f2b6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "embeddings",
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index("ix_embeddings_content_hash", "embeddings", ["content_hash"])
    # The temporary server default only guarantees the NOT NULL for pre-existing
    # (empty) rows; application inserts always provide a real hash.
    op.alter_column("embeddings", "content_hash", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_embeddings_content_hash", table_name="embeddings")
    op.drop_column("embeddings", "content_hash")