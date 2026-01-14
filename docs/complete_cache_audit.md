# Complete Cache Migration Audit

## ✅ Already Migrated to PostgreSQL

### 1. AI Recommendations (43 rows)
- **Source**: `cache/ai_recommendations.db` → `ai_recommendations` table
- **Destination**: PostgreSQL `ai_recommendations` table
- **Status**: ✅ MIGRATED
- **Model**: `app/models/analytics/ai_recommendation.py`

### 2. Top Picks Runs (42 rows)
- **Source**: `cache/top_picks_runs.db` → `top_picks_runs` table
- **Destination**: PostgreSQL `top_picks_runs` table
- **Status**: ✅ MIGRATED
- **Model**: `app/models/analytics/top_picks_run.py`

### 3. LLM Costs (0 rows, but structure exists)
- **Source**: `cache/llm_costs.db` → `llm_requests` table
- **Destination**: PostgreSQL `llm_requests` table
- **Status**: ✅ MIGRATED (will populate on use)
- **Model**: `app/models/analytics/llm_request.py`

---

## 🔄 NEEDS MIGRATION - SQLite to Redis/PostgreSQL

### 1. Support/Resistance Levels
- **Current**: `cache/top_picks_runs.db` → `support_resistance_levels` table (0 rows)
- **Service**: `services/support_resistance_service.py`
- **Recommendation**: **MIGRATE TO REDIS** (cache data, frequently computed)
- **Target**: Redis namespace `fyntrix:support_resistance`
- **Action Required**: Update `SupportResistanceService` to use Redis

### 2. Context Storage
- **Current**: `cache/context.db` (not created yet, will be on use)
  - `agent_analyses` table
  - `context_memory` table
  - `user_preferences` table
  - `agent_learnings` table
- **Service**: `context/storage.py`
- **Recommendation**: 
  - `agent_analyses` → **PostgreSQL** (already have model)
  - `agent_learnings` → **PostgreSQL** (already have model)
  - `context_memory` → **REDIS** (short-term cache with TTL)
  - `user_preferences` → **PostgreSQL** (already have UserPreferences model)
- **Action Required**: Update `ContextStorage` class

### 3. Pick Events (in ai_recommendations.db)
- **Current**: `cache/ai_recommendations.db`
  - `pick_events` (0 rows)
  - `pick_agent_contributions` (0 rows)
  - `pick_outcomes` (0 rows)
  - `rl_policies` (0 rows)
- **Status**: ✅ Already have PostgreSQL models in `app/models/trading.py`
- **Action Required**: Update `services/pick_logger.py` to use PostgreSQL (if not already done)

---

## ✅ Already Using Redis (via redis_client.py)

### Redis Keys Currently in Use:
1. **Top Picks Cache**
   - `top_picks:{universe}:{mode}` (e.g., `top_picks:nifty50:intraday`)
   - Written by: `top_picks_scheduler.py`
   - Read by: `routers/agents.py`, `routers/cache.py`, `routers/scalping.py`
   - **Status**: ✅ WORKING

2. **Locks**
   - `lock:top_picks:{universe}:{mode}`
   - Used by: `top_picks_scheduler.py`
   - **Status**: ✅ WORKING

3. **Dashboard Aggregates**
   - `dashboard:overview:intraday`
   - `dashboard:overview:performance:7d`
   - Written by: `dashboard_scheduler.py`
   - Read by: `routers/cache.py`
   - **Status**: ✅ WORKING

4. **Scalping Monitor**
   - `scalping:monitor:last`
   - Written by: `scalping_monitor_scheduler.py`
   - Read by: `routers/cache.py`, `routers/scalping.py`
   - **Status**: ✅ WORKING

5. **Portfolio Monitoring**
   - `portfolio:monitor:positions:last`
   - `portfolio:monitor:watchlist:last`
   - Written by: `portfolio_monitor_scheduler.py`
   - Read by: `routers/cache.py`
   - **Status**: ✅ WORKING

6. **Top Picks Positions Monitoring**
   - `top_picks:monitor:positions:last`
   - Written by: `top_picks_positions_monitor_scheduler.py`
   - Read by: `routers/cache.py`
   - **Status**: ✅ WORKING

---

## 📁 File-Based Persistence

### Historical Pick Runs
- **Location**: `backend/data/top_picks_intraday/picks_{universe}_MODE_YYYYMMDD_HHMMSS.json`
- **Status**: ❌ NOT FOUND (directory doesn't exist yet)
- **Recommendation**: Keep as files (historical archive), but also store metadata in PostgreSQL
- **Action**: No migration needed (will be created when picks are generated)

---

## 🎯 Migration Action Plan

### Phase 1: Support/Resistance Service → Redis ✅
1. Update `SupportResistanceService` to use Redis instead of SQLite
2. Use Redis hashes for efficient storage
3. Keep TTL-based expiration

### Phase 2: Context Storage → PostgreSQL + Redis ✅
1. Update `ContextStorage` to use:
   - PostgreSQL for `agent_analyses`, `agent_learnings`, `user_preferences`
   - Redis for `context_memory` (short-term cache)
2. Migrate any existing data

### Phase 3: Consolidate Redis Clients ✅
1. Keep existing `redis_client.py` (already working)
2. Update new `redis_cache.py` to use same connection
3. Ensure no conflicts

### Phase 4: Verify All APIs ✅
1. Test top picks endpoints
2. Test dashboard endpoints
3. Test scalping endpoints
4. Test cache endpoints
5. Test agent endpoints

---

## 📊 Summary

**Total Cache Systems**: 10
- ✅ **Migrated to PostgreSQL**: 3 (ai_recommendations, top_picks_runs, llm_requests)
- ✅ **Already using Redis**: 6 (top_picks, locks, dashboard, scalping, portfolio, positions)
- 🔄 **Needs Migration**: 2 (support_resistance, context_storage)
- 📁 **File-based (OK)**: 1 (historical pick files)

**Next Steps**:
1. Migrate Support/Resistance service to Redis
2. Migrate Context Storage to PostgreSQL + Redis
3. Test all APIs
4. Document final state
