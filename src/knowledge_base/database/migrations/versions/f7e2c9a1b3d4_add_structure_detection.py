"""add structure detection schema

Revision ID: f7e2c9a1b3d4
Revises: 44d8e71f7328
Create Date: 2026-09-13 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7e2c9a1b3d4'
down_revision: Union[str, Sequence[str], None] = '44d8e71f7328'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Block types the structure detector can emit. Enum values are additive;
    # PostgreSQL does not support dropping enum values, so the downgrade keeps
    # them (they are unused once the column reverts).
    op.execute("ALTER TYPE kb_blocktype ADD VALUE IF NOT EXISTS 'page_number'")
    op.execute("ALTER TYPE kb_blocktype ADD VALUE IF NOT EXISTS 'front_matter'")
    op.execute("ALTER TYPE kb_blocktype ADD VALUE IF NOT EXISTS 'toc_entry'")
    op.execute("ALTER TYPE kb_blocktype ADD VALUE IF NOT EXISTS 'reference'")

    op.execute(
        "CREATE TYPE kb_chapterkind AS ENUM "
        "('chapter', 'front_matter', 'table_of_contents', 'appendix')"
    )

    op.add_column(
        'chapters',
        sa.Column(
            'kind',
            sa.Enum('chapter', 'front_matter', 'table_of_contents', 'appendix',
                    name='kb_chapterkind'),
            server_default='chapter',
            nullable=False,
        ),
    )

    op.create_table(
        'subsections',
        sa.Column('book_id', sa.Uuid(), nullable=False),
        sa.Column('section_id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('source_file_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ),
        sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ),
        sa.ForeignKeyConstraint(['source_file_id'], ['source_files.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('section_id', 'number', name='uq_subsections_section_number'),
    )
    op.create_index('ix_subsections_book_id', 'subsections', ['book_id'], unique=False)
    op.create_index('ix_subsections_section_id', 'subsections', ['section_id'], unique=False)

    op.add_column(
        'content_blocks',
        sa.Column('subsection_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_content_blocks_subsection_id',
        'content_blocks',
        'subsections',
        ['subsection_id'],
        ['id'],
    )
    op.create_index(
        'ix_content_blocks_subsection_id', 'content_blocks', ['subsection_id'], unique=False
    )
    op.add_column('content_blocks', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('content_blocks', 'notes')
    op.drop_index('ix_content_blocks_subsection_id', table_name='content_blocks')
    op.drop_constraint('fk_content_blocks_subsection_id', 'content_blocks', type_='foreignkey')
    op.drop_column('content_blocks', 'subsection_id')
    op.drop_index('ix_subsections_section_id', table_name='subsections')
    op.drop_index('ix_subsections_book_id', table_name='subsections')
    op.drop_table('subsections')
    op.drop_column('chapters', 'kind')
    op.execute("DROP TYPE IF EXISTS kb_chapterkind")
    # kb_blocktype additions cannot be dropped in PostgreSQL; they are simply
    # no longer produced once the detector reverts.