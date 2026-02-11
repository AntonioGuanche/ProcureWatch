"""007 – add subscription/billing columns to users table."""

revision = "007"
down_revision = "006"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan", sa.String(20), server_default="free", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("subscription_status", sa.String(30), server_default="none", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "subscription_ends_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "plan")
