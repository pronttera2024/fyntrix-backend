# Database Architecture Audit - Complete Analysis

**Date:** January 14, 2026  
**Status:** ✅ All tables accounted for

---

## 🗄️ Database Architecture Overview

Your application uses **TWO separate database systems**:

1. **Main Application Database (RDS PostgreSQL)** - User data, trading, authentication
2. **Cache Databases (SQLite)** - AI recommendations, LLM costs, temporary data

---

## 📊 Main Application Database (RDS PostgreSQL)

**Connection:** `postgresql://fintrixAdmin:***@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require`

### Tables in RDS (9 tables) ✅

| Table | Purpose | Model Location | Status |
|-------|---------|----------------|--------|
| `alembic_version` | Migration tracking | N/A (Alembic) | ✅ System |
| `users` | User authentication & profile | `app/models/user.py` | ✅ Migrated |
| `user_preferences` | User settings & preferences | `app/models/user_preferences.py` | ✅ Migrated |
| `user_watchlists` | User watchlist entries | `app/models/watchlist.py` | ✅ Migrated |
| `broker_connections` | Broker account connections | `app/db_models/trading.py` | ✅ Migrated |
| `broker_tokens` | Encrypted broker tokens | `app/db_models/trading.py` | ✅ Migrated |
| `trade_intents` | Trade intentions | `app/db_models/trading.py` | ✅ Migrated |
| `broker_orders` | Actual broker orders | `app/db_models/trading.py` | ✅ Migrated |
| `portfolio_snapshots` | Portfolio state snapshots | `app/db_models/trading.py` | ✅ Migrated |

### SQLAlchemy Models → RDS Tables Mapping

```python
# app/models/user.py
class User(Base):
    __tablename__ = "users"
    ✅ Migrated via: migrations/versions/0002_create_enhanced_users_table.py

# app/models/user_preferences.py
class UserPreferences(Base):
    __tablename__ = "user_preferences"
    ✅ Migrated via: migrations/versions/0003_user_preferences.py

# app/models/watchlist.py
class UserWatchlist(Base):
    __tablename__ = "user_watchlists"
    ✅ Migrated via: migrations/versions/0004_user_watchlists.py

# app/db_models/trading.py
class BrokerConnection(Base):
    __tablename__ = "broker_connections"
class BrokerToken(Base):
    __tablename__ = "broker_tokens"
class TradeIntent(Base):
    __tablename__ = "trade_intents"
class BrokerOrder(Base):
    __tablename__ = "broker_orders"
class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    ✅ Migrated via: migrations/versions/0001_exec_trading_tables.py
```

**Result:** ✅ **All SQLAlchemy models are migrated to RDS PostgreSQL**

---

## 💾 Cache Databases (SQLite - Separate System)

These are **NOT** part of the main application database. They are separate SQLite files used for caching and AI features.

### 1. `cache/llm_costs.db` - LLM Cost Tracking

**Purpose:** Track OpenAI API usage and costs  
**Managed by:** `app/llm/cost_tracker.py` (uses raw SQLite, not SQLAlchemy)  
**Migration:** ❌ Not needed - this is a cache database

**Tables:**
- `llm_requests` - API request logs with costs
  - Columns: id, model, tokens_input, tokens_output, cost_usd, created_at

**Usage:**
```python
from app.llm.cost_tracker import cost_tracker
await cost_tracker.log_request('gpt-4', 100, 50)
```

---

### 2. `cache/ai_recommendations.db` - AI Recommendations Cache

**Purpose:** Store AI-generated stock recommendations and outcomes  
**Managed by:** Various AI agents (uses raw SQLite, not SQLAlchemy)  
**Migration:** ❌ Not needed - this is a cache database

**Tables:**
- `ai_recommendations` - AI stock picks and recommendations
- `pick_agent_contributions` - Individual agent contributions to picks
- `pick_events` - Trading signal events
- `pick_outcomes` - Evaluation results of picks
- `rl_policies` - Reinforcement learning policies

**Schema Details:**

#### `ai_recommendations` (28 columns)
- id, symbol, mode, universe, source, recommendation, direction
- generated_at_utc, entry_price, stop_loss_price, target_price
- score_blend, confidence, risk_profile, run_id, rank_in_run
- policy_version, features_json, evaluated, evaluated_at_utc
- exit_price, exit_time_utc, exit_reason, pnl_pct
- max_drawdown_pct, alpha_vs_benchmark, labels_json

#### `pick_agent_contributions` (5 columns)
- id, pick_uuid, agent_name, score, confidence, metadata

#### `pick_events` (22 columns)
- id, pick_uuid, symbol, direction, source, mode
- signal_ts, trade_date, signal_price
- recommended_entry, recommended_target, recommended_stop
- time_horizon, blend_score, recommendation, confidence
- regime, risk_profile_bucket, mode_bucket, universe, extra_context

#### `pick_outcomes` (17 columns)
- id, pick_uuid, evaluation_horizon, horizon_end_ts
- price_close, price_high, price_low
- ret_close_pct, max_runup_pct, max_drawdown_pct
- benchmark_symbol, benchmark_ret_pct, ret_vs_benchmark_pct
- hit_target, hit_stop, outcome_label, notes

#### `rl_policies` (11 columns)
- id, policy_id, name, description
- created_at, updated_at, status, config_json, metrics_json
- activated_at, deactivated_at

---

## 🔍 Why Cache Databases Are Separate

### Design Rationale

1. **Performance:** SQLite is faster for local caching and doesn't require network calls
2. **Cost:** No need to store temporary cache data in expensive RDS
3. **Isolation:** Cache failures don't affect main application database
4. **Simplicity:** No migrations needed for cache schemas
5. **Ephemeral:** Cache data can be deleted/recreated without data loss

### Cache vs Main Database Decision Matrix

| Data Type | Storage | Reason |
|-----------|---------|--------|
| User accounts | RDS | Persistent, critical |
| User preferences | RDS | Persistent, sync across devices |
| Watchlists | RDS | Persistent, sync across devices |
| Broker connections | RDS | Persistent, critical |
| Trading orders | RDS | Persistent, audit trail |
| AI recommendations | SQLite Cache | Temporary, regenerated daily |
| LLM costs | SQLite Cache | Monitoring, can be aggregated |
| Pick outcomes | SQLite Cache | Analysis, can be archived |

---

## 📋 Summary

### Main Database (RDS PostgreSQL)
✅ **9 tables total**
- 1 system table (alembic_version)
- 3 user tables (users, user_preferences, user_watchlists)
- 5 trading tables (broker_connections, broker_tokens, trade_intents, broker_orders, portfolio_snapshots)

✅ **All SQLAlchemy models migrated**
✅ **All migrations applied**
✅ **SSL enabled**
✅ **Production ready**

### Cache Databases (SQLite)
💾 **2 cache databases**
- `cache/llm_costs.db` - 1 table (llm_requests)
- `cache/ai_recommendations.db` - 5 tables (ai_recommendations, pick_agent_contributions, pick_events, pick_outcomes, rl_policies)

❌ **No migration needed** - These are intentionally separate cache databases
✅ **Working as designed**

---

## 🎯 Conclusion

**Your database architecture is complete and correct!**

- **Main application data** → RDS PostgreSQL (persistent, scalable, multi-environment)
- **Cache/temporary data** → SQLite files (fast, local, disposable)

**No missing tables. No additional migrations needed.**

The cache databases in SQLite are **by design** and should remain separate from your main RDS database. They serve different purposes and have different lifecycle requirements.

---

## 📝 Next Steps

1. ✅ **Database Setup** - Complete
2. ✅ **Migrations** - All applied
3. ✅ **API Endpoints** - Created (preferences, watchlist)
4. 🚀 **Ready for Development** - Start building features
5. 📊 **Frontend Integration** - Share API documentation with frontend team

---

## 🔧 Maintenance Notes

### Cache Database Cleanup

The cache databases can grow over time. Consider periodic cleanup:

```python
# Clean old LLM cost records (older than 90 days)
from app.llm.cost_tracker import cost_tracker
cost_tracker.cleanup_old_records(days=90)

# AI recommendations cache can be cleared/archived as needed
# No automatic cleanup - managed by AI agents
```

### Backup Strategy

- **RDS PostgreSQL:** Automated backups via AWS (7-day retention)
- **SQLite Caches:** No backup needed (regenerated data)

### Monitoring

- **RDS:** Monitor via AWS CloudWatch
- **Caches:** Monitor disk space usage in `cache/` directory

---

**Architecture Status:** ✅ Production Ready  
**Last Updated:** January 14, 2026
