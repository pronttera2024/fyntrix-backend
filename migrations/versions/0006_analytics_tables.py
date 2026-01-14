"""Analytics tables for LLM costs, AI recommendations, top picks, and agent context

Revision ID: 0006_analytics_tables
Revises: 0005_trading_data
Create Date: 2026-01-14 14:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006_analytics_tables'
down_revision = '0005_trading_data'
branch_labels = None
depends_on = None


def upgrade():
    # Create llm_requests table
    op.create_table(
        'llm_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('tokens_input', sa.Integer(), nullable=True),
        sa.Column('tokens_output', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_llm_requests_created_at', 'llm_requests', ['created_at'])
    op.create_index('idx_llm_requests_model', 'llm_requests', ['model'])
    op.create_index('idx_llm_requests_model_date', 'llm_requests', ['model', 'created_at'])

    # Create ai_recommendations table
    op.create_table(
        'ai_recommendations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('mode', sa.String(length=50), nullable=False),
        sa.Column('universe', sa.String(length=50), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('recommendation', sa.String(length=50), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('generated_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('stop_loss_price', sa.Float(), nullable=True),
        sa.Column('target_price', sa.Float(), nullable=True),
        sa.Column('score_blend', sa.Float(), nullable=True),
        sa.Column('confidence', sa.String(length=20), nullable=True),
        sa.Column('risk_profile', sa.String(length=50), nullable=True),
        sa.Column('run_id', sa.String(length=100), nullable=True),
        sa.Column('rank_in_run', sa.Integer(), nullable=True),
        sa.Column('policy_version', sa.String(length=100), nullable=True),
        sa.Column('features_json', sa.Text(), nullable=True),
        sa.Column('evaluated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('evaluated_at_utc', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('exit_time_utc', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_reason', sa.String(length=100), nullable=True),
        sa.Column('pnl_pct', sa.Float(), nullable=True),
        sa.Column('max_drawdown_pct', sa.Float(), nullable=True),
        sa.Column('alpha_vs_benchmark', sa.Float(), nullable=True),
        sa.Column('labels_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_ai_rec_symbol', 'ai_recommendations', ['symbol'])
    op.create_index('idx_ai_rec_mode', 'ai_recommendations', ['mode'])
    op.create_index('idx_ai_rec_generated_at', 'ai_recommendations', ['generated_at_utc'])
    op.create_index('idx_ai_rec_symbol_mode_time', 'ai_recommendations', ['symbol', 'mode', 'generated_at_utc'])
    op.create_index('idx_ai_rec_evaluated', 'ai_recommendations', ['evaluated'])
    op.create_index('idx_ai_rec_evaluated_time', 'ai_recommendations', ['evaluated', 'generated_at_utc'])
    op.create_index('idx_ai_rec_run_id', 'ai_recommendations', ['run_id'])
    op.create_index('idx_ai_rec_source', 'ai_recommendations', ['source'])

    # Create top_picks_runs table
    op.create_table(
        'top_picks_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=100), nullable=False),
        sa.Column('universe', sa.String(length=50), nullable=False),
        sa.Column('mode', sa.String(length=50), nullable=False),
        sa.Column('picks_json', sa.Text(), nullable=False),
        sa.Column('elapsed_seconds', sa.Integer(), nullable=True),
        sa.Column('pick_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id')
    )
    op.create_index('idx_top_picks_run_id', 'top_picks_runs', ['run_id'])
    op.create_index('idx_top_picks_universe', 'top_picks_runs', ['universe'])
    op.create_index('idx_top_picks_mode', 'top_picks_runs', ['mode'])
    op.create_index('idx_top_picks_universe_mode_time', 'top_picks_runs', ['universe', 'mode', 'created_at'])
    op.create_index('idx_top_picks_created_at', 'top_picks_runs', ['created_at'])

    # Create agent_analyses table
    op.create_table(
        'agent_analyses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('agent_type', sa.String(length=100), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('confidence', sa.String(length=20), nullable=True),
        sa.Column('signals', sa.Text(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('analysis_metadata', sa.Text(), nullable=True),
        sa.Column('global_context', sa.Text(), nullable=True),
        sa.Column('policy_context', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_agent_analysis_symbol', 'agent_analyses', ['symbol'])
    op.create_index('idx_agent_analysis_agent_type', 'agent_analyses', ['agent_type'])
    op.create_index('idx_agent_analysis_symbol_date', 'agent_analyses', ['symbol', 'created_at'])
    op.create_index('idx_agent_analysis_agent_symbol', 'agent_analyses', ['agent_type', 'symbol', 'created_at'])

    # Create agent_learnings table
    op.create_table(
        'agent_learnings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_type', sa.String(length=100), nullable=False),
        sa.Column('pattern_recognized', sa.String(length=255), nullable=False),
        sa.Column('accuracy', sa.Float(), nullable=True),
        sa.Column('sample_size', sa.Integer(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_agent_learning_agent_type', 'agent_learnings', ['agent_type'])
    op.create_index('idx_agent_learning_updated', 'agent_learnings', ['last_updated'])


def downgrade():
    # Drop tables in reverse order
    op.drop_index('idx_agent_learning_updated', table_name='agent_learnings')
    op.drop_index('idx_agent_learning_agent_type', table_name='agent_learnings')
    op.drop_table('agent_learnings')

    op.drop_index('idx_agent_analysis_agent_symbol', table_name='agent_analyses')
    op.drop_index('idx_agent_analysis_symbol_date', table_name='agent_analyses')
    op.drop_index('idx_agent_analysis_agent_type', table_name='agent_analyses')
    op.drop_index('idx_agent_analysis_symbol', table_name='agent_analyses')
    op.drop_table('agent_analyses')

    op.drop_index('idx_top_picks_created_at', table_name='top_picks_runs')
    op.drop_index('idx_top_picks_universe_mode_time', table_name='top_picks_runs')
    op.drop_index('idx_top_picks_mode', table_name='top_picks_runs')
    op.drop_index('idx_top_picks_universe', table_name='top_picks_runs')
    op.drop_index('idx_top_picks_run_id', table_name='top_picks_runs')
    op.drop_table('top_picks_runs')

    op.drop_index('idx_ai_rec_source', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_run_id', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_evaluated_time', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_evaluated', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_symbol_mode_time', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_generated_at', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_mode', table_name='ai_recommendations')
    op.drop_index('idx_ai_rec_symbol', table_name='ai_recommendations')
    op.drop_table('ai_recommendations')

    op.drop_index('idx_llm_requests_model_date', table_name='llm_requests')
    op.drop_index('idx_llm_requests_model', table_name='llm_requests')
    op.drop_index('idx_llm_requests_created_at', table_name='llm_requests')
    op.drop_table('llm_requests')
