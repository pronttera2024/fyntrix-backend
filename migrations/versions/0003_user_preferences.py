"""Create user_preferences table

Revision ID: 0003_user_preferences
Revises: 0002_create_enhanced_users_table
Create Date: 2026-01-14

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0003_user_preferences"
down_revision = "0002_create_enhanced_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(length=255), nullable=False, comment="User ID (FK to users)"),
        sa.Column("disclosure_accepted", sa.Boolean(), nullable=False, server_default=sa.false(), comment="Whether user accepted disclosure"),
        sa.Column("disclosure_version", sa.String(length=20), nullable=True, comment="Version of disclosure accepted (e.g., v1)"),
        sa.Column("universe", sa.String(length=50), nullable=False, server_default="NIFTY50", comment="Stock universe (NIFTY50, NIFTY500, etc.)"),
        sa.Column("market_region", sa.String(length=20), nullable=False, server_default="India", comment="Market region (India, Global)"),
        sa.Column("risk_profile", sa.String(length=20), nullable=False, server_default="Moderate", comment="Risk profile (Aggressive, Moderate, Conservative)"),
        sa.Column("trading_modes", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="Trading modes as JSON object"),
        sa.Column("primary_mode", sa.String(length=20), nullable=True, comment="Primary trading mode"),
        sa.Column("auxiliary_modes", postgresql.JSON(astext_type=sa.Text()), nullable=True, comment="Auxiliary trading modes as JSON array"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Preferences creation timestamp"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Last update timestamp"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    
    # Create indexes for frequently queried columns
    op.create_index("ix_user_preferences_universe", "user_preferences", ["universe"])
    op.create_index("ix_user_preferences_risk_profile", "user_preferences", ["risk_profile"])
    op.create_index("ix_user_preferences_market_region", "user_preferences", ["market_region"])


def downgrade() -> None:
    op.drop_index("ix_user_preferences_market_region", table_name="user_preferences")
    op.drop_index("ix_user_preferences_risk_profile", table_name="user_preferences")
    op.drop_index("ix_user_preferences_universe", table_name="user_preferences")
    op.drop_table("user_preferences")
