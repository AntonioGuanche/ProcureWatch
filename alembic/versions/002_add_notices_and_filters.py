"""add notices and filters

Revision ID: 002
Revises: 001
Create Date: 2026-01-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create filters table
    op.create_table(
        'filters',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('keywords', sa.String(length=500), nullable=True),
        sa.Column('cpv_prefixes', sa.String(length=200), nullable=True),
        sa.Column('countries', sa.String(length=100), nullable=True),
        sa.Column('buyer_keywords', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create notices table
    op.create_table(
        'notices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('buyer_name', sa.String(length=255), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=True),
        sa.Column('language', sa.String(length=2), nullable=True),
        sa.Column('cpv', sa.String(length=20), nullable=True),
        sa.Column('procedure_type', sa.String(length=100), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('deadline_at', sa.DateTime(), nullable=True),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('raw_json', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uq_notice_source_source_id')
    )

    # Create indexes
    op.create_index('ix_notices_published_at', 'notices', ['published_at'])
    op.create_index('ix_notices_deadline_at', 'notices', ['deadline_at'])
    op.create_index('ix_notices_cpv', 'notices', ['cpv'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_notices_cpv', table_name='notices')
    op.drop_index('ix_notices_deadline_at', table_name='notices')
    op.drop_index('ix_notices_published_at', table_name='notices')

    # Drop tables
    op.drop_table('notices')
    op.drop_table('filters')
