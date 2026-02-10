"""006 – add is_admin column to users table."""

revision = "006"
down_revision = "005"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
