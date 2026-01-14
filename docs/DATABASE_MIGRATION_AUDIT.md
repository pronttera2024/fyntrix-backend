# Database Migration Audit & localStorage Analysis

## 📊 Current Database State

### Existing SQLAlchemy Models

#### 1. **Trading Models** (`app/db_models/trading.py`)
- ✅ **BrokerConnection** - Broker account connections
- ✅ **BrokerToken** - Encrypted access/refresh tokens
- ✅ **TradeIntent** - User trade intentions
- ✅ **BrokerOrder** - Actual broker orders
- ✅ **PortfolioSnapshot** - Portfolio state snapshots

#### 2. **User Model** (`app/models/user.py`)
- ✅ **User** - User authentication and profile (NEW - needs migration)

#### 3. **Strategy Models** (`app/models/strategy.py`)
- ⚠️ **StrategyProfile** - Pydantic model (NOT a database table)
- ⚠️ **StrategyAdvisory** - Pydantic model (NOT a database table)

### Existing Migrations

#### Migration 0001: Trading Tables (ALREADY EXISTS)
- ✅ broker_connections
- ✅ broker_tokens
- ✅ trade_intents
- ✅ broker_orders
- ✅ portfolio_snapshots

#### Migration 0002: Users Table (NEW - READY TO RUN)
- 🆕 users (with comprehensive audit fields)

---

## 🗄️ SQLite Database Analysis

### Local SQLite Files Found:
1. `fyntrix_local.db` - **EMPTY** (no tables)
2. `cache/ai_recommendations.db` - **NOT A DATABASE** (file format issue)
3. `cache/llm_costs.db` - **NOT A DATABASE** (file format issue)
4. `cache/top_picks_runs.db` - **NOT A DATABASE** (file format issue)

**Conclusion**: No existing data in SQLite to migrate. All cache files are not valid SQLite databases.

---

## 💾 Frontend localStorage Usage Analysis

### Critical Data Stored in localStorage (Frontend: `App.tsx`)

#### **1. Market Data** (Real-time/Cached)
```javascript
localStorage.getItem('arise_market')           // Market indices data
localStorage.getItem('arise_flows')            // Market flows data
localStorage.getItem('arise_market_asof')      // Market data timestamp
localStorage.getItem('arise_spark')            // Sparkline data
```

#### **2. News & Events**
```javascript
localStorage.getItem('arise_news')             // News articles array
localStorage.getItem('arise_events')           // Market events
```

#### **3. User Preferences** (NEEDS API)
```javascript
localStorage.getItem('arise_disclosure_accepted_v1')  // Disclosure acceptance
localStorage.getItem('arise_account_profile_v1')      // {name, account_id}
localStorage.getItem('arise_universe')                // 'NIFTY50', 'NIFTY500', etc.
localStorage.getItem('arise_market_region')           // 'India' | 'Global'
localStorage.getItem('arise_risk')                    // 'Aggressive'|'Moderate'|'Conservative'
localStorage.getItem('arise_modes')                   // {Intraday, Swing, Options, Futures}
localStorage.getItem('arise_primary_mode')            // Primary trading mode
localStorage.getItem('arise_auxiliary_modes')         // Array of auxiliary modes
```

#### **4. AI Picks & Strategy Cache** (Session/Temporary)
```javascript
localStorage.getItem('arise_picks')            // AI stock picks
localStorage.getItem('arise_winning_trades')   // Winning trades data
localStorage.getItem('arise_strategy_cache_v1') // Strategy execution cache
localStorage.getItem('arise_dismissed_insights_v1') // Dismissed insight IDs
```

#### **5. Watchlist** (NEEDS API)
```javascript
localStorage.getItem('arise_watchlist')        // User's watchlist symbols
```

---

## 🎯 Migration Strategy

### Phase 1: Database Tables (IMMEDIATE)
All trading tables already have migrations. Need to:
1. ✅ Run migration 0001 (trading tables) - ALREADY EXISTS
2. ✅ Run migration 0002 (users table) - READY TO RUN
3. ✅ Verify all tables created in RDS

### Phase 2: User Preferences API (HIGH PRIORITY)
Create new table and APIs for:
- **user_preferences** table
  - user_id (FK to users)
  - disclosure_accepted
  - universe (NIFTY50, NIFTY500, etc.)
  - market_region (India, Global)
  - risk_profile (Aggressive, Moderate, Conservative)
  - trading_modes (JSON: {Intraday, Swing, Options, Futures})
  - primary_mode
  - auxiliary_modes (JSON array)
  - created_at, updated_at

### Phase 3: Watchlist API (HIGH PRIORITY)
Create new table and APIs for:
- **user_watchlists** table
  - id (PK)
  - user_id (FK to users)
  - symbol
  - exchange
  - added_at
  - notes (optional)

### Phase 4: Dismissed Insights API (MEDIUM PRIORITY)
Create new table and APIs for:
- **user_dismissed_insights** table
  - user_id (FK to users)
  - insight_id
  - dismissed_at

---

## 📝 Required Actions

### Backend Changes

#### 1. Create Migration 0003: User Preferences Table
```python
# migrations/versions/0003_user_preferences.py
- user_preferences table
- Indexes on user_id, universe, risk_profile
```

#### 2. Create Migration 0004: User Watchlists Table
```python
# migrations/versions/0004_user_watchlists.py
- user_watchlists table
- Indexes on user_id, symbol
- Unique constraint on (user_id, symbol)
```

#### 3. Create Migration 0005: User Dismissed Insights Table
```python
# migrations/versions/0005_user_dismissed_insights.py
- user_dismissed_insights table
- Composite primary key (user_id, insight_id)
```

#### 4. Create SQLAlchemy Models
- `app/models/user_preferences.py`
- `app/models/watchlist.py`
- `app/models/user_insights.py`

#### 5. Create API Endpoints

**User Preferences:**
- `GET /api/v1/preferences` - Get user preferences
- `PUT /api/v1/preferences` - Update user preferences
- `PATCH /api/v1/preferences` - Partial update

**Watchlist:**
- `GET /api/v1/watchlist` - Get user watchlist
- `POST /api/v1/watchlist` - Add symbol to watchlist
- `DELETE /api/v1/watchlist/{symbol}` - Remove from watchlist
- `PUT /api/v1/watchlist` - Bulk update watchlist

**Dismissed Insights:**
- `GET /api/v1/insights/dismissed` - Get dismissed insights
- `POST /api/v1/insights/{insight_id}/dismiss` - Dismiss insight
- `DELETE /api/v1/insights/{insight_id}/dismiss` - Un-dismiss insight

---

## 🔄 Frontend Migration Path (FOR FRONTEND TEAM)

### Step 1: Add API Integration (No UI Changes)
```typescript
// Replace localStorage calls with API calls
// Example:
// OLD: localStorage.getItem('arise_preferences')
// NEW: await api.get('/api/v1/preferences')
```

### Step 2: Implement Fallback Strategy
```typescript
// During transition, read from localStorage if API fails
// This ensures no data loss during migration
```

### Step 3: Data Migration Script
```typescript
// One-time script to migrate existing localStorage data to backend
// Run on first login after API deployment
```

### Step 4: Remove localStorage Dependencies
```typescript
// After successful migration, remove all localStorage calls
// Keep only session-level caching if needed
```

---

## 🚀 Deployment Sequence

### Development Environment
1. Run all migrations on dev RDS
2. Deploy backend APIs
3. Test API endpoints
4. Update frontend to use APIs (with localStorage fallback)
5. Test end-to-end flow

### Staging Environment
1. Run migrations on staging RDS
2. Deploy backend
3. Deploy frontend with migration script
4. Verify data migration from localStorage to backend

### Production Environment
1. Run migrations on production RDS
2. Deploy backend APIs
3. Deploy frontend with migration script
4. Monitor migration success rate
5. Gradual rollout with feature flags

---

## 📊 Data That Should REMAIN in localStorage

### Session/Temporary Data (OK to keep in localStorage)
- `arise_picks` - AI picks (refreshed frequently)
- `arise_market` - Market data (real-time cache)
- `arise_flows` - Market flows (real-time cache)
- `arise_news` - News (real-time cache)
- `arise_spark` - Sparklines (real-time cache)
- `arise_strategy_cache_v1` - Strategy execution cache (session-level)
- `arise_winning_trades` - Winning trades (refreshed frequently)

### Persistent Data (MUST move to backend)
- ✅ User preferences (risk, modes, universe)
- ✅ Watchlist
- ✅ Dismissed insights
- ✅ Account profile (should come from auth/user API)
- ✅ Disclosure acceptance

---

## 🎯 Success Metrics

1. **Zero Data Loss**: All user preferences migrated successfully
2. **Performance**: API response time < 200ms for preferences
3. **Reliability**: 99.9% uptime for preference APIs
4. **User Experience**: Seamless transition, no user action required
5. **Multi-Environment**: Same code works across dev/staging/prod

---

## 🔐 Security Considerations

1. **Authentication**: All APIs require valid JWT token
2. **Authorization**: Users can only access their own data
3. **Data Validation**: Pydantic schemas for all inputs
4. **Rate Limiting**: Prevent abuse of preference APIs
5. **Audit Trail**: Log all preference changes with timestamps

---

## 📅 Timeline Estimate

- **Phase 1** (Database Tables): 2 hours
  - Create migrations
  - Run migrations
  - Verify tables

- **Phase 2** (User Preferences API): 4 hours
  - Create models
  - Create endpoints
  - Write tests
  - Deploy

- **Phase 3** (Watchlist API): 3 hours
  - Create models
  - Create endpoints
  - Write tests
  - Deploy

- **Phase 4** (Frontend Integration): 8 hours (FRONTEND TEAM)
  - API integration
  - Migration script
  - Testing
  - Deployment

**Total Backend Effort**: ~9 hours
**Total Frontend Effort**: ~8 hours (separate team)

---

## ✅ Next Steps (In Order)

1. ✅ Run existing migrations (0001, 0002)
2. 🔄 Create user_preferences migration and model
3. 🔄 Create user_preferences API endpoints
4. 🔄 Create watchlist migration and model
5. 🔄 Create watchlist API endpoints
6. 🔄 Create dismissed_insights migration and model
7. 🔄 Create dismissed_insights API endpoints
8. 🔄 Write API tests
9. 🔄 Deploy to dev environment
10. 🔄 Provide frontend team with API documentation
