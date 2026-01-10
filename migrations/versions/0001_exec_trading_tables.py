"""Create broker execution persistence tables

Revision ID: 0001_exec_trading_tables
Revises: 
Create Date: 2026-01-01

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_exec_trading_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_connections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DISCONNECTED"),
        sa.Column("client_user_id", sa.String(length=128), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_broker_connections_account_id", "broker_connections", ["account_id"])
    op.create_index("ix_broker_connections_broker", "broker_connections", ["broker"])

    op.create_table(
        "broker_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("broker_connection_id", sa.String(length=36), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["broker_connection_id"], ["broker_connections.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_broker_tokens_connection", "broker_tokens", ["broker_connection_id"])

    op.create_table(
        "trade_intents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=True),
        sa.Column("segment", sa.String(length=8), nullable=False),
        sa.Column("product", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.String(length=8), nullable=False),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("trigger_price", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_trade_intents_account_id", "trade_intents", ["account_id"])
    op.create_index("ix_trade_intents_session_id", "trade_intents", ["session_id"])
    op.create_index("ix_trade_intents_symbol", "trade_intents", ["symbol"])
    op.create_index("ix_trade_intents_state", "trade_intents", ["state"])

    op.create_table(
        "broker_orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trade_intent_id", sa.String(length=36), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("filled_qty", sa.Integer(), nullable=True),
        sa.Column("average_price", sa.Float(), nullable=True),
        sa.Column("raw_response_redacted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["trade_intent_id"], ["trade_intents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_broker_orders_trade_intent", "broker_orders", ["trade_intent_id"])
    op.create_index("ix_broker_orders_broker", "broker_orders", ["broker"])
    op.create_index("ix_broker_orders_broker_order_id", "broker_orders", ["broker_order_id"])
    op.create_index("ix_broker_orders_status", "broker_orders", ["status"])

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=128), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_portfolio_snapshots_account_id", "portfolio_snapshots", ["account_id"])
    op.create_index("ix_portfolio_snapshots_broker", "portfolio_snapshots", ["broker"])
    op.create_index("ix_portfolio_snapshots_kind", "portfolio_snapshots", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_kind", table_name="portfolio_snapshots")
    op.drop_index("ix_portfolio_snapshots_broker", table_name="portfolio_snapshots")
    op.drop_index("ix_portfolio_snapshots_account_id", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")

    op.drop_index("ix_broker_orders_status", table_name="broker_orders")
    op.drop_index("ix_broker_orders_broker_order_id", table_name="broker_orders")
    op.drop_index("ix_broker_orders_broker", table_name="broker_orders")
    op.drop_index("ix_broker_orders_trade_intent", table_name="broker_orders")
    op.drop_table("broker_orders")

    op.drop_index("ix_trade_intents_state", table_name="trade_intents")
    op.drop_index("ix_trade_intents_symbol", table_name="trade_intents")
    op.drop_index("ix_trade_intents_session_id", table_name="trade_intents")
    op.drop_index("ix_trade_intents_account_id", table_name="trade_intents")
    op.drop_table("trade_intents")

    op.drop_index("ix_broker_tokens_connection", table_name="broker_tokens")
    op.drop_table("broker_tokens")

    op.drop_index("ix_broker_connections_broker", table_name="broker_connections")
    op.drop_index("ix_broker_connections_account_id", table_name="broker_connections")
    op.drop_table("broker_connections")
