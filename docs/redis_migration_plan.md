# Cache & Database Migration Plan

## 🎯 **CRITICAL DECISION: PostgreSQL vs Redis**

### **PostgreSQL** (Persistent, Analytical, Transactional Data)
- Requires ACID guarantees
- Historical analytics and reporting
- Audit trails and billing data
- User preferences and settings
- Machine learning training data

### **Redis** (Temporary, High-Speed Cache)
- Short-lived data with TTL
- Computed scores and rankings
- Session data
- Rate limiting
- Real-time market data cache

---

## 📊 Current Cache Systems Inventory

### 1. **SQLite → PostgreSQL** (Persistent Data - MIGRATE TO DB FIRST)

#### A. **LLM Cost Tracker** (`app/llm/cost_tracker.py`) ⚠️ **→ PostgreSQL**
- **Current**: `cache/llm_costs.db` (SQLite)
- **Purpose**: Track OpenAI API usage and costs
- **Why PostgreSQL**: 
  - Billing/audit data (must persist)
  - Financial reporting requirements
  - Historical cost analysis
  - Budget tracking and alerts
- **Tables**:
  - `llm_requests` (id, model, tokens_input, tokens_output, cost_usd, created_at)
- **Operations**:
  - Log API requests with token usage
  - Get daily spend
  - Get usage statistics (7-day breakdown)
  - Check budget alerts
  - Cleanup old records (90+ days)
- **Migration Strategy**: Create PostgreSQL models + Alembic migration
- **Priority**: HIGH - Financial data must be persistent

#### B. **AI Recommendation Store** (`app/services/ai_recommendation_store.py`) ⚠️ **→ PostgreSQL**
- **Current**: `cache/ai_recommendations.db` (SQLite)
- **Purpose**: Store AI trade recommendations for performance analytics
- **Why PostgreSQL**:
  - Performance analytics and ML training data
  - Historical recommendation tracking
  - Complex queries (filters, aggregations)
  - Backtesting and strategy evaluation
- **Tables**:
  - `ai_recommendations` (symbol, mode, universe, entry/exit prices, PnL, etc.)
- **Operations**:
  - Log recommendations from top picks
  - Apply scalping exits
  - Fetch dataset with filters
  - Track evaluated vs unevaluated picks
- **Migration Strategy**: Create PostgreSQL models + Alembic migration
- **Priority**: HIGH - Core analytics data

#### C. **Top Picks Store** (`app/services/top_picks_store.py`) ⚠️ **→ PostgreSQL**
- **Current**: `cache/top_picks_runs.db` (SQLite)
- **Purpose**: Store top picks runs for different universes/modes
- **Why PostgreSQL**:
  - Historical picks tracking for performance analysis
  - Audit trail of recommendations
  - Time-series analysis of pick quality
  - Regulatory compliance (recommendation history)
- **Tables**:
  - `top_picks_runs` (run_id, universe, mode, picks_json, created_at)
- **Operations**:
  - Save top picks runs
  - Get latest picks by universe/mode (can cache in Redis)
  - Get run by ID
  - List recent runs
  - Cleanup old runs (archive, not delete)
- **Migration Strategy**: Create PostgreSQL models + Alembic migration
- **Note**: Latest picks can be cached in Redis with 5-min TTL
- **Priority**: HIGH - Core business data

#### D. **Context Storage** (`app/context/storage.py`) ⚠️ **→ PostgreSQL + Redis Hybrid**
- **Current**: `cache/context.db` (SQLite)
- **Purpose**: Store agent analyses, user preferences, context memory
- **Why PostgreSQL**:
  - User preferences (persistent settings)
  - Agent analyses (historical performance tracking)
  - Agent learnings (ML training data)
- **Why Redis**:
  - Context memory (temporary, TTL-based)
  - Session data
- **Tables**:
  - **PostgreSQL**: `agent_analyses`, `user_preferences`, `agent_learnings`
  - **Redis**: `context_memory` (with TTL)
- **Operations**:
  - Store/retrieve agent analyses → PostgreSQL
  - Manage context memory with TTL → Redis
  - Store user preferences → PostgreSQL (already exists in main DB)
  - Track agent learning patterns → PostgreSQL
- **Migration Strategy**: Split into PostgreSQL models + Redis cache
- **Priority**: MEDIUM - Hybrid approach

#### E. **Pick Logger** (`app/services/pick_logger.py`)
- **Database**: `cache/pick_events.db`
- **Purpose**: Log pick events, outcomes, and RL policies
- **Tables**:
  - `pick_events` (pick_uuid, symbol, mode, entry_price, agents_json)
  - `pick_agent_contributions` (pick_uuid, agent_name, score, weight)
  - `pick_outcomes` (pick_uuid, evaluation_horizon, pnl, returns)
  - `rl_policies` (policy_id, name, config_json, metrics_json, status)
- **Operations**:
  - Log pick events with agent contributions
  - Log pick outcomes
  - Create/activate RL policies
  - Compute outcomes for date ranges
- **Migration Strategy**: Already migrated to PostgreSQL ORM (pick_logger_orm.py)
- **Status**: ✅ COMPLETED - Using PostgreSQL with SQLAlchemy

#### F. **Support/Resistance Service** (`app/services/support_resistance_service.py`) ✅ **→ Redis**
- **Current**: `cache/support_resistance.db` (SQLite)
- **Purpose**: Cache support/resistance levels for symbols
- **Why Redis**:
  - Computed values (can be recalculated)
  - Short TTL (market data changes)
  - High-speed access required
- **Tables**:
  - `sr_levels` (symbol, timeframe, levels_json, updated_at)
- **Operations**:
  - Get/set support/resistance levels
  - Cache with TTL (1-4 hours)
- **Migration Strategy**: Redis Hashes with TTL
- **Priority**: LOW - Pure cache data

#### G. **Historical Data Cache** (`app/services/historical_cache.py`) ✅ **→ Redis**
- **Current**: File-based cache in `.cache/historical/`
- **Purpose**: Cache historical OHLC data
- **Why Redis**:
  - Temporary cache (data from external APIs)
  - Can be refetched if needed
  - High-speed access for chart rendering
- **Operations**:
  - Generate cache keys (symbol, date range, interval)
  - Store/retrieve cached data with TTL
  - Smart TTL based on timeframe (1m=1hr, 1d=24hr)
  - Cache statistics tracking
- **Migration Strategy**: Redis Strings (JSON) with TTL
- **Priority**: MEDIUM - Improves API response times

#### H. **Global Score Store** (`app/services/global_score_store.py`) ✅ **→ Redis**
- **Current**: File-based cache in `data/global_scores/score_cache.json`
- **Purpose**: Maintain single source of truth for stock scores
- **Why Redis**:
  - Computed scores (recalculated every 6 hours)
  - Market session cache
  - Shared across multiple backend instances
- **Operations**:
  - Cache stock scores across universes
  - 6-hour TTL (market session)
  - In-memory + file persistence
- **Migration Strategy**: Redis Hashes with TTL
- **Priority**: HIGH - Critical for top picks performance

### 2. **In-Memory Caches** (Need Migration to Redis)

#### I. **General Cache Service** (`app/services/cache.py`) ✅ **→ Redis**
- **Current**: In-memory dictionary `_MEMORY_CACHE`
- **Purpose**: Generic caching with market hours awareness
- **Why Redis**:
  - Temporary cache data
  - Shared across instances
  - TTL-based expiration
- **Operations**:
  - Get cached value with TTL
  - Persist to disk for last trading day → Redis persistence
  - Market hours detection
  - Clear memory cache
- **Migration Strategy**: Redis with TTL + Pub/Sub for cache invalidation
- **Priority**: HIGH - Core caching infrastructure

#### J. **Memory Manager** (`app/context/memory.py`) ✅ **→ Redis**
- **Current**: In-memory dictionaries
- **Purpose**: Short-term and working memory for agents
- **Why Redis**:
  - Session data (temporary)
  - Working memory (ephemeral)
  - Shared state across instances
- **Operations**:
  - Session data with TTL
  - Working memory/context
  - Cache for frequently accessed data
- **Migration Strategy**: Redis with TTL + Namespacing
- **Priority**: MEDIUM - Session management

---

## 🎯 REVISED Migration Strategy

### **PHASE 0: PostgreSQL Migrations (DO THIS FIRST!)**

#### **Step 1: LLM Cost Tracker → PostgreSQL**
- Create models: `LLMRequest`
- Migration: `0006_llm_cost_tracking.py`
- Update service to use ORM
- Priority: HIGH

#### **Step 2: AI Recommendation Store → PostgreSQL**
- Create models: `AIRecommendation`
- Migration: `0007_ai_recommendations.py`
- Update service to use ORM
- Priority: HIGH

#### **Step 3: Top Picks Store → PostgreSQL**
- Create models: `TopPicksRun`
- Migration: `0008_top_picks_runs.py`
- Update service to use ORM
- Priority: HIGH

#### **Step 4: Context Storage → PostgreSQL (Partial)**
- Create models: `AgentAnalysis`, `AgentLearning`
- Migration: `0009_agent_context.py`
- Update service to use ORM for persistent data
- Priority: MEDIUM

---

### **PHASE 1: Redis Infrastructure Setup**
1. Add Redis to dependencies (`requirements.txt`)
2. Configure Redis connection (environment variables)
3. Create Redis client wrapper with connection pooling
4. Add Redis health check endpoint

### **PHASE 2: Redis Cache Migrations**
1. **RedisCache** - Base cache adapter with common operations
2. **RedisSupportResistance** - Replace S/R SQLite DB
3. **RedisHistoricalCache** - Replace file-based cache
4. **RedisScoreStore** - Replace global score cache
5. **RedisMemoryManager** - Replace in-memory caches
6. **RedisGeneralCache** - Replace general cache service
7. **RedisContextMemory** - Replace context memory (TTL-based)

### **PHASE 3: Testing & Validation**
1. Verify PostgreSQL migrations
2. Test Redis cache operations
3. Performance benchmarking
4. Test cache hit rates

### Phase 4: Cutover
1. Switch reads to Redis
2. Monitor for issues
3. Deprecate SQLite writes
4. Remove SQLite dependencies

### Phase 5: Cleanup
1. Remove SQLite database files
2. Remove old cache code
3. Update documentation
4. Performance optimization

---

## 📋 Redis Data Structure Design

### LLM Cost Tracker
```
# Daily spend tracking
llm:daily:{date} -> Hash {total_cost, total_requests, total_input_tokens, total_output_tokens}

# Request log (sorted set by timestamp)
llm:requests -> Sorted Set (score=timestamp, member=request_id)
llm:request:{request_id} -> Hash {model, tokens_input, tokens_output, cost_usd, created_at}

# Model statistics
llm:model:{model}:{date} -> Hash {requests, cost}
```

### AI Recommendations
```
# Recommendations by symbol and mode
rec:symbol:{symbol}:{mode} -> Sorted Set (score=timestamp, member=rec_id)
rec:{rec_id} -> Hash {all recommendation fields}

# Unevaluated recommendations
rec:unevaluated -> Sorted Set (score=timestamp, member=rec_id)

# Run-based recommendations
rec:run:{run_id} -> Set {rec_id1, rec_id2, ...}
```

### Top Picks
```
# Latest picks by universe and mode
picks:latest:{universe}:{mode} -> String (JSON payload) + TTL

# Run history
picks:runs -> Sorted Set (score=timestamp, member=run_id)
picks:run:{run_id} -> Hash {universe, mode, picks_json, created_at}
```

### Context Storage
```
# Agent analyses
context:analysis:{symbol}:{agent_type} -> Hash {score, confidence, signals, reasoning, created_at}

# Context memory with TTL
context:memory:{context_type}:{key} -> String (JSON) + TTL

# User preferences
context:user:{user_id}:{pref_key} -> String (JSON)

# Agent learnings
context:learning:{agent_type} -> Hash {pattern, accuracy, sample_size, last_updated}
```

### Historical Data Cache
```
# OHLC data cache
hist:{symbol}:{from_date}:{to_date}:{interval} -> String (JSON) + TTL

# Cache metadata
hist:meta -> Hash {hits, misses, writes}
```

### Global Score Store
```
# Stock scores
scores:global:{symbol} -> Hash {score, timestamp, agent_scores_json}

# Cache timestamp
scores:cache_timestamp -> String (ISO timestamp)
```

### Support/Resistance
```
# S/R levels
sr:{symbol}:{timeframe} -> String (JSON) + TTL
```

---

## 🔧 Implementation Checklist

### Infrastructure
- [ ] Add `redis` and `redis-py` to requirements.txt
- [ ] Add Redis environment variables (REDIS_URL, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)
- [ ] Create `app/cache/redis_client.py` - Redis connection manager
- [ ] Create `app/cache/base.py` - Base cache adapter interface
- [ ] Add Redis health check to `/health` endpoint

### Core Cache Services
- [ ] Create `app/cache/redis_llm_cost_tracker.py`
- [ ] Create `app/cache/redis_recommendation_store.py`
- [ ] Create `app/cache/redis_top_picks_store.py`
- [ ] Create `app/cache/redis_context_storage.py`
- [ ] Create `app/cache/redis_support_resistance.py`
- [ ] Create `app/cache/redis_historical_cache.py`
- [ ] Create `app/cache/redis_score_store.py`
- [ ] Create `app/cache/redis_memory_manager.py`
- [ ] Create `app/cache/redis_general_cache.py`

### Migration Scripts
- [ ] Create `scripts/migrate_llm_costs_to_redis.py`
- [ ] Create `scripts/migrate_recommendations_to_redis.py`
- [ ] Create `scripts/migrate_top_picks_to_redis.py`
- [ ] Create `scripts/migrate_context_to_redis.py`
- [ ] Create `scripts/migrate_sr_levels_to_redis.py`

### Service Updates
- [ ] Update `app/llm/cost_tracker.py` to use Redis
- [ ] Update `app/services/ai_recommendation_store.py` to use Redis
- [ ] Update `app/services/top_picks_store.py` to use Redis
- [ ] Update `app/context/storage.py` to use Redis
- [ ] Update `app/context/memory.py` to use Redis
- [ ] Update `app/services/support_resistance_service.py` to use Redis
- [ ] Update `app/services/historical_cache.py` to use Redis
- [ ] Update `app/services/global_score_store.py` to use Redis
- [ ] Update `app/services/cache.py` to use Redis

### Testing
- [ ] Unit tests for Redis adapters
- [ ] Integration tests for cache operations
- [ ] Performance benchmarks (SQLite vs Redis)
- [ ] Load testing for concurrent access
- [ ] Failover testing (Redis unavailable)

### Documentation
- [ ] Update README with Redis setup instructions
- [ ] Document Redis data structures
- [ ] Create cache migration guide
- [ ] Update deployment documentation

### Deployment
- [ ] Add Redis to Docker Compose
- [ ] Configure Redis on Render.com
- [ ] Set up Redis monitoring
- [ ] Configure Redis persistence (RDB + AOF)
- [ ] Set up Redis backup strategy

---

## 📈 Expected Benefits

1. **Performance**: 10-100x faster than SQLite for concurrent operations
2. **Scalability**: Horizontal scaling with Redis Cluster
3. **Distributed**: Share cache across multiple backend instances
4. **TTL Management**: Native expiration support
5. **Pub/Sub**: Real-time cache invalidation
6. **Data Structures**: Rich data types (Sets, Sorted Sets, Hashes)
7. **Atomic Operations**: Thread-safe operations
8. **Monitoring**: Built-in stats and monitoring

---

## ⚠️ Migration Risks & Mitigation

### Risk 1: Data Loss During Migration
**Mitigation**: Dual-write to both SQLite and Redis during transition

### Risk 2: Redis Connection Failures
**Mitigation**: Implement fallback to SQLite, circuit breaker pattern

### Risk 3: Memory Limits
**Mitigation**: Configure Redis maxmemory policy (allkeys-lru)

### Risk 4: Data Inconsistency
**Mitigation**: Implement cache versioning, validation checks

### Risk 5: Performance Degradation
**Mitigation**: Connection pooling, pipelining, monitoring

---

## 🚀 Next Steps

1. **Review this plan** with the team
2. **Set up Redis instance** (local + production)
3. **Start with Phase 1** - Infrastructure setup
4. **Implement one service at a time** - Start with simplest (cache.py)
5. **Test thoroughly** before moving to next service
6. **Monitor metrics** throughout migration

---

**Status**: 📝 Planning Complete - Ready for Implementation
**Estimated Effort**: 2-3 weeks (1 service per day)
**Priority**: High - Improves performance and scalability
