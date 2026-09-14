"""Add normalized Arabic full-text search vector for ayahs

Revision ID: e5b1a0f4c3d2
Revises: d7a52e1f9c4b
Create Date: 2026-09-14

Qur'anic orthography uses Unicode variants (alef-wasla U+0671, superscript
alef U+0670, hamza-carrying alefs, alef-maksura) plus heavy diacritics, which
defeat verbatim ``simple`` token matching. ``ayahs.search_vector_norm`` stores
a ``simple`` tsvector over diacritic-stripped, letter-normalized Arabic so a
plain query (``الرحمن``) matches stored text (``ٱلرَّحْمَٰنِ``). The column is
populated by the seed/backfill layer (see ``knowledge_base/search/arabic.py``);
tests exercise the same path via ``create_all`` + backfill.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5b1a0f4c3d2"
down_revision = "d7a52e1f9c4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ayahs",
        sa.Column("search_vector_norm", postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index(
        "ix_ayahs_search_vector_norm",
        "ayahs",
        ["search_vector_norm"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_ayahs_search_vector_norm", table_name="ayahs")
    op.drop_column("ayahs", "search_vector_norm")