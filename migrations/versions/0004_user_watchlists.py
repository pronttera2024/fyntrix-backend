"""Create user_watchlists table

Revision ID: 0004_user_watchlists
Revises: 0003_user_preferences
Create Date: 2026-01-14

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_user_watchlists"
down_revision = "0003_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_watchlists",
        sa.Column("id", sa.String(length=36), nullable=False, comment="Watchlist entry ID"),
        sa.Column("user_id", sa.String(length=255), nullable=False, comment="User ID (FK to users)"),
        sa.Column("symbol", sa.String(length=50), nullable=False, comment="Stock symbol (e.g., RELIANCE, TCS)"),
        sa.Column("exchange", sa.String(length=20), nullable=True, comment="Exchange (NSE, BSE, etc.)"),
        sa.Column("notes", sa.Text(), nullable=True, comment="User notes about this stock"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="When stock was added to watchlist"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    
    # Create indexes
    op.create_index("ix_user_watchlists_user_id", "user_watchlists", ["user_id"])
    op.create_index("ix_user_watchlists_symbol", "user_watchlists", ["symbol"])
    
    # Create unique constraint on user_id + symbol
    op.create_index("ix_user_watchlists_user_symbol", "user_watchlists", ["user_id", "symbol"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_watchlists_user_symbol", table_name="user_watchlists")
    op.drop_index("ix_user_watchlists_symbol", table_name="user_watchlists")
    op.drop_index("ix_user_watchlists_user_id", table_name="user_watchlists")
    op.drop_table("user_watchlists")
