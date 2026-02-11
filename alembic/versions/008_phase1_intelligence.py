"""008 – Phase 1 Intelligence: CAN award fields, relevance scoring, AI summaries.

Adds:
  notices: award_winner_name, award_value, award_date, number_tenders_received,
           award_criteria_json, ai_summary, ai_summary_lang, ai_summary_generated_at
  watchlist_matches: relevance_score
  users: ai_usage_count, ai_usage_reset_at
"""

revision = "008"
down_revision = "007"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # -- notices: CAN award data --
    op.add_column("notices", sa.Column("award_winner_name", sa.String(500), nullable=True))
    op.add_column("notices", sa.Column("award_value", sa.Numeric(18, 2), nullable=True))
    op.add_column("notices", sa.Column("award_date", sa.Date(), nullable=True))
    op.add_column("notices", sa.Column("number_tenders_received", sa.Integer(), nullable=True))
    op.add_column("notices", sa.Column("award_criteria_json", sa.JSON(), nullable=True))

    # -- notices: AI summary --
    op.add_column("notices", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("notices", sa.Column("ai_summary_lang", sa.String(5), nullable=True))
    op.add_column("notices", sa.Column("ai_summary_generated_at", sa.DateTime(), nullable=True))

    # -- watchlist_matches: relevance score --
    op.add_column("watchlist_matches", sa.Column("relevance_score", sa.Integer(), nullable=True))

    # -- users: AI usage tracking --
    op.add_column("users", sa.Column("ai_usage_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("ai_usage_reset_at", sa.DateTime(), nullable=True))

    # Indexes for award data queries
    op.create_index("ix_notices_award_date", "notices", ["award_date"])
    op.create_index("ix_notices_notice_type_award", "notices", ["notice_type", "award_date"])


def downgrade() -> None:
    op.drop_index("ix_notices_notice_type_award", table_name="notices")
    op.drop_index("ix_notices_award_date", table_name="notices")

    op.drop_column("users", "ai_usage_reset_at")
    op.drop_column("users", "ai_usage_count")
    op.drop_column("watchlist_matches", "relevance_score")
    op.drop_column("notices", "ai_summary_generated_at")
    op.drop_column("notices", "ai_summary_lang")
    op.drop_column("notices", "ai_summary")
    op.drop_column("notices", "award_criteria_json")
    op.drop_column("notices", "number_tenders_received")
    op.drop_column("notices", "award_date")
    op.drop_column("notices", "award_value")
    op.drop_column("notices", "award_winner_name")
