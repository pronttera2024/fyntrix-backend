"""Monitoring tables for historical tracking

Revision ID: 0007_monitoring_tables
Revises: 0006_analytics_tables
Create Date: 2026-01-14 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0007_monitoring_tables'
down_revision = '0006_analytics_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Create dashboard_performance table
    op.create_table(
        'dashboard_performance',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('period_type', sa.String(length=20), nullable=False),
        sa.Column('total_recommendations', sa.Integer(), nullable=True),
        sa.Column('evaluated_count', sa.Integer(), nullable=True),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('avg_pnl_pct', sa.Float(), nullable=True),
        sa.Column('total_pnl_pct', sa.Float(), nullable=True),
        sa.Column('metrics_json', postgresql.JSONB(), nullable=True),
        sa.Column('recommendations_json', postgresql.JSONB(), nullable=True),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dashboard_performance_period_type', 'dashboard_performance', ['period_type'])
    op.create_index('ix_dashboard_performance_snapshot_at', 'dashboard_performance', ['snapshot_at'])

    # Create portfolio_snapshots table
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('snapshot_type', sa.String(length=50), nullable=False),
        sa.Column('total_positions', sa.Integer(), nullable=True),
        sa.Column('total_value', sa.Float(), nullable=True),
        sa.Column('total_pnl', sa.Float(), nullable=True),
        sa.Column('total_pnl_pct', sa.Float(), nullable=True),
        sa.Column('positions_json', postgresql.JSONB(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_portfolio_snapshots_snapshot_type', 'portfolio_snapshots', ['snapshot_type'])
    op.create_index('ix_portfolio_snapshots_snapshot_at', 'portfolio_snapshots', ['snapshot_at'])
    op.create_index('idx_portfolio_snapshot_type_time', 'portfolio_snapshots', ['snapshot_type', 'snapshot_at'])

    # Create top_picks_position_snapshots table
    op.create_table(
        'top_picks_position_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('universe', sa.String(length=50), nullable=False),
        sa.Column('mode', sa.String(length=50), nullable=False),
        sa.Column('total_positions', sa.Integer(), nullable=True),
        sa.Column('active_positions', sa.Integer(), nullable=True),
        sa.Column('total_pnl', sa.Float(), nullable=True),
        sa.Column('total_pnl_pct', sa.Float(), nullable=True),
        sa.Column('win_count', sa.Integer(), nullable=True),
        sa.Column('loss_count', sa.Integer(), nullable=True),
        sa.Column('positions_json', postgresql.JSONB(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=True),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_top_picks_position_snapshots_universe', 'top_picks_position_snapshots', ['universe'])
    op.create_index('ix_top_picks_position_snapshots_mode', 'top_picks_position_snapshots', ['mode'])
    op.create_index('ix_top_picks_position_snapshots_snapshot_at', 'top_picks_position_snapshots', ['snapshot_at'])
    op.create_index('idx_tpps_universe_mode_time', 'top_picks_position_snapshots', ['universe', 'mode', 'snapshot_at'])


def downgrade():
    op.drop_table('top_picks_position_snapshots')
    op.drop_table('portfolio_snapshots')
    op.drop_table('dashboard_performance')
