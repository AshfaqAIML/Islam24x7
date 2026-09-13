"""chunk fields for content_chunks

Revision ID: b62e5a8c1d7f
Revises: a91c4d2f6e08
Create Date: 2026-09-13 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b62e5a8c1d7f'
down_revision: Union[str, Sequence[str], None] = 'a91c4d2f6e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # chunks now group several paragraphs; the single (block, sequence)
    # uniqueness is replaced by the global chunk_id uniqueness.
    op.drop_constraint(
        'uq_content_chunks_block_seq', 'content_chunks', type_='unique'
    )

    op.add_column(
        'content_chunks',
        sa.Column(
            'chapter_id',
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.add_column(
        'content_chunks',
        sa.Column(
            'section_id',
            sa.Uuid(),
            nullable=True,
        ),
    )
    op.add_column(
        'content_chunks',
        sa.Column(
            'language',
            sa.Enum('ar', 'ur', 'en', 'other', name='kb_language', create_type=False),
            nullable=False,
        ),
    )
    op.add_column(
        'content_chunks',
        sa.Column('token_count', sa.Integer(), nullable=False),
    )
    op.add_column(
        'content_chunks',
        sa.Column('page_start', sa.Integer(), nullable=True),
    )
    op.add_column(
        'content_chunks',
        sa.Column('page_end', sa.Integer(), nullable=True),
    )
    op.add_column(
        'content_chunks',
        sa.Column(
            'metadata_',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        'content_chunks',
        sa.Column(
            'is_normalized',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )

    op.create_foreign_key(
        'fk_content_chunks_chapter_id',
        'content_chunks',
        'chapters',
        ['chapter_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_content_chunks_section_id',
        'content_chunks',
        'sections',
        ['section_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_content_chunks_section_id', 'content_chunks', type_='foreignkey')
    op.drop_constraint('fk_content_chunks_chapter_id', 'content_chunks', type_='foreignkey')
    op.drop_column('content_chunks', 'is_normalized')
    op.drop_column('content_chunks', 'metadata_')
    op.drop_column('content_chunks', 'page_end')
    op.drop_column('content_chunks', 'page_start')
    op.drop_column('content_chunks', 'token_count')
    op.drop_column('content_chunks', 'language')
    op.drop_column('content_chunks', 'section_id')
    op.drop_column('content_chunks', 'chapter_id')
    op.create_unique_constraint(
        'uq_content_chunks_block_seq',
        'content_chunks',
        ['content_block_id', 'sequence'],
    )