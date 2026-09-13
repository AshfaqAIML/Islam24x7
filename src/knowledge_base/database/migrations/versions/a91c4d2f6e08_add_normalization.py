"""add normalization schema

Revision ID: a91c4d2f6e08
Revises: f7e2c9a1b3d4
Create Date: 2026-09-13 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a91c4d2f6e08'
down_revision: Union[str, Sequence[str], None] = 'f7e2c9a1b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'normalized_texts',
        sa.Column('content_block_id', sa.Uuid(), nullable=False),
        sa.Column('book_id', sa.Uuid(), nullable=False),
        sa.Column('source_file_id', sa.Uuid(), nullable=False),
        sa.Column(
            'language',
            postgresql.ENUM('ar', 'ur', 'en', 'other', name='kb_language', create_type=False),
            nullable=False,
        ),
        sa.Column('config_name', sa.Text(), nullable=False),
        sa.Column('normalized_text', sa.Text(), nullable=False),
        sa.Column('original_sha256', sa.Text(), nullable=False),
        sa.Column('protected', sa.Boolean(), nullable=False),
        sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['book_id'], ['books.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['content_block_id'], ['content_blocks.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['source_file_id'], ['source_files.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'content_block_id', name='uq_normalized_texts_content_block',
        ),
    )
    op.create_index(
        'ix_normalized_texts_book_id', 'normalized_texts', ['book_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_normalized_texts_book_id', table_name='normalized_texts')
    op.drop_table('normalized_texts')