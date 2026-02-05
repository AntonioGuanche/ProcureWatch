"""add publicprocurement fields

Revision ID: 003
Revises: 002
Create Date: 2026-01-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to notices table
    op.add_column('notices', sa.Column('cpv_main_code', sa.String(length=20), nullable=True))
    op.add_column('notices', sa.Column('first_seen_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
    op.add_column('notices', sa.Column('last_seen_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
    
    # Create index on cpv_main_code
    op.create_index('ix_notices_cpv_main_code', 'notices', ['cpv_main_code'])
    
    # Create notice_cpv_additional table
    op.create_table(
        'notice_cpv_additional',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notice_id', sa.String(length=36), nullable=False),
        sa.Column('cpv_code', sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['notice_id'], ['notices.id'], ondelete='CASCADE')
    )
    
    # Create index on notice_id for faster lookups
    op.create_index('ix_notice_cpv_additional_notice_id', 'notice_cpv_additional', ['notice_id'])


def downgrade() -> None:
    # Drop table and indexes
    op.drop_index('ix_notice_cpv_additional_notice_id', table_name='notice_cpv_additional')
    op.drop_table('notice_cpv_additional')
    op.drop_index('ix_notices_cpv_main_code', table_name='notices')
    op.drop_column('notices', 'last_seen_at')
    op.drop_column('notices', 'first_seen_at')
    op.drop_column('notices', 'cpv_main_code')
