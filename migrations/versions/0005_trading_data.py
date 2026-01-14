# Create trading data tables (pick_events, pick_agent_contributions, pick_outcomes, rl_policies)

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0005_trading_data"
down_revision = "0004_user_watchlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create pick_events table
    op.create_table(
        "pick_events",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("pick_uuid", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("signal_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("signal_price", sa.Float(), nullable=False),
        sa.Column("recommended_entry", sa.Float(), nullable=True),
        sa.Column("recommended_target", sa.Float(), nullable=True),
        sa.Column("recommended_stop", sa.Float(), nullable=True),
        sa.Column("time_horizon", sa.String(length=20), nullable=True),
        sa.Column("blend_score", sa.Float(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("regime", sa.String(length=50), nullable=True),
        sa.Column("risk_profile_bucket", sa.String(length=20), nullable=True),
        sa.Column("mode_bucket", sa.String(length=20), nullable=True),
        sa.Column("universe", sa.String(length=50), nullable=True),
        sa.Column("extra_context", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pick_uuid", name="uq_pick_events_pick_uuid"),
    )

    # Create indexes for pick_events
    op.create_index("idx_pick_events_pick_uuid", "pick_events", ["pick_uuid"])
    op.create_index("idx_pick_events_symbol", "pick_events", ["symbol"])
    op.create_index("idx_pick_events_trade_date", "pick_events", ["trade_date"])
    op.create_index("idx_pick_events_symbol_date", "pick_events", ["symbol", "trade_date"])

    # Create pick_agent_contributions table
    op.create_table(
        "pick_agent_contributions",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("pick_uuid", sa.String(length=36), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("agent_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pick_uuid"], ["pick_events.pick_uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for pick_agent_contributions
    op.create_index("idx_pick_agent_contrib_pick_uuid", "pick_agent_contributions", ["pick_uuid"])
    op.create_index("idx_pick_agent_contrib_agent", "pick_agent_contributions", ["agent_name"])

    # Create pick_outcomes table
    op.create_table(
        "pick_outcomes",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("pick_uuid", sa.String(length=36), nullable=False),
        sa.Column("evaluation_horizon", sa.String(length=20), nullable=False),
        sa.Column("horizon_end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_close", sa.Float(), nullable=True),
        sa.Column("price_high", sa.Float(), nullable=True),
        sa.Column("price_low", sa.Float(), nullable=True),
        sa.Column("ret_close_pct", sa.Float(), nullable=True),
        sa.Column("max_runup_pct", sa.Float(), nullable=True),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=True),
        sa.Column("benchmark_symbol", sa.String(length=20), nullable=True),
        sa.Column("benchmark_ret_pct", sa.Float(), nullable=True),
        sa.Column("ret_vs_benchmark_pct", sa.Float(), nullable=True),
        sa.Column("hit_target", sa.Boolean(), nullable=True),
        sa.Column("hit_stop", sa.Boolean(), nullable=True),
        sa.Column("outcome_label", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pick_uuid"], ["pick_events.pick_uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pick_uuid", "evaluation_horizon", name="uq_pick_outcome"),
    )

    # Create indexes for pick_outcomes
    op.create_index("idx_pick_outcomes_pick_uuid", "pick_outcomes", ["pick_uuid"])
    op.create_index("idx_pick_outcomes_label", "pick_outcomes", ["outcome_label"])

    # Create rl_policies table
    op.create_table(
        "rl_policies",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("policy_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", name="uq_rl_policies_policy_id"),
    )

    # Create indexes for rl_policies
    op.create_index("idx_rl_policies_policy_id", "rl_policies", ["policy_id"])
    op.create_index("idx_rl_policies_status", "rl_policies", ["status"])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("idx_rl_policies_status", table_name="rl_policies")
    op.drop_index("idx_rl_policies_policy_id", table_name="rl_policies")
    op.drop_index("idx_pick_outcomes_label", table_name="pick_outcomes")
    op.drop_index("idx_pick_outcomes_pick_uuid", table_name="pick_outcomes")
    op.drop_index("idx_pick_agent_contrib_agent", table_name="pick_agent_contributions")
    op.drop_index("idx_pick_agent_contrib_pick_uuid", table_name="pick_agent_contributions")
    op.drop_index("idx_pick_events_symbol_date", table_name="pick_events")
    op.drop_index("idx_pick_events_trade_date", table_name="pick_events")
    op.drop_index("idx_pick_events_symbol", table_name="pick_events")
    op.drop_index("idx_pick_events_pick_uuid", table_name="pick_events")

    # Drop tables in reverse order (due to foreign key constraints)
    op.drop_table("rl_policies")
    op.drop_table("pick_outcomes")
    op.drop_table("pick_agent_contributions")
    op.drop_table("pick_events")
