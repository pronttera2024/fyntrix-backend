# Frontend API Documentation - localStorage Migration

## 🎯 Overview

This document provides the API specifications for migrating localStorage data to backend APIs. All APIs require JWT authentication via the `Authorization: Bearer <token>` header.

**Base URL**: `https://fyntrix-backend-8ym9.onrender.com` (Production)  
**Base URL**: `http://localhost:8000` (Development)

---

## 🔐 Authentication

All endpoints require a valid JWT token from AWS Cognito authentication.

```typescript
// Add to all API requests
headers: {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json'
}
```

---

## 📊 User Preferences API

### **GET /api/v1/preferences**

Get user preferences (creates default preferences if none exist).

**Response:**
```json
{
  "user_id": "uuid",
  "disclosure_accepted": false,
  "disclosure_version": "v1",
  "universe": "NIFTY50",
  "market_region": "India",
  "risk_profile": "Moderate",
  "trading_modes": {
    "Intraday": false,
    "Swing": true,
    "Options": false,
    "Futures": false
  },
  "primary_mode": "Swing",
  "auxiliary_modes": [],
  "created_at": "2026-01-14T12:00:00Z",
  "updated_at": "2026-01-14T12:00:00Z"
}
```

**localStorage Mapping:**
```typescript
// OLD localStorage keys → NEW API response
localStorage.getItem('arise_disclosure_accepted_v1') → response.disclosure_accepted
localStorage.getItem('arise_universe') → response.universe
localStorage.getItem('arise_market_region') → response.market_region
localStorage.getItem('arise_risk') → response.risk_profile
localStorage.getItem('arise_modes') → response.trading_modes
localStorage.getItem('arise_primary_mode') → response.primary_mode
localStorage.getItem('arise_auxiliary_modes') → response.auxiliary_modes
```

---

### **PUT /api/v1/preferences**

Update user preferences (full or partial update).

**Request Body:**
```json
{
  "disclosure_accepted": true,
  "disclosure_version": "v1",
  "universe": "NIFTY500",
  "market_region": "Global",
  "risk_profile": "Aggressive",
  "trading_modes": {
    "Intraday": true,
    "Swing": true,
    "Options": true,
    "Futures": false
  },
  "primary_mode": "Intraday",
  "auxiliary_modes": ["Swing", "Options"]
}
```

**Response:** Same as GET response

**Usage Example:**
```typescript
// Update preferences when user changes settings
const updatePreferences = async (updates: Partial<Preferences>) => {
  const response = await fetch('/api/v1/preferences', {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(updates)
  });
  return response.json();
};

// Example: Update universe
await updatePreferences({ universe: 'NIFTY500' });
```

---

### **PATCH /api/v1/preferences**

Partially update user preferences (same as PUT, semantically indicates partial update).

**Request Body:** Same as PUT (all fields optional)

**Response:** Same as GET response

---

## 📋 Watchlist API

### **GET /api/v1/watchlist**

Get user's watchlist (all symbols).

**Response:**
```json
[
  {
    "id": "uuid",
    "user_id": "uuid",
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "notes": "Strong fundamentals",
    "added_at": "2026-01-14T12:00:00Z",
    "updated_at": "2026-01-14T12:00:00Z"
  },
  {
    "id": "uuid",
    "user_id": "uuid",
    "symbol": "TCS",
    "exchange": "NSE",
    "notes": null,
    "added_at": "2026-01-14T11:00:00Z",
    "updated_at": "2026-01-14T11:00:00Z"
  }
]
```

**localStorage Mapping:**
```typescript
// OLD localStorage
const watchlist = JSON.parse(localStorage.getItem('arise_watchlist') || '[]');
// watchlist = ['RELIANCE', 'TCS', 'INFY']

// NEW API response
const watchlist = response.map(item => item.symbol);
// watchlist = ['RELIANCE', 'TCS', 'INFY']
```

---

### **POST /api/v1/watchlist**

Add a symbol to watchlist.

**Request Body:**
```json
{
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "notes": "Strong fundamentals"
}
```

**Response:** Single watchlist entry (same structure as GET response item)

**Status Codes:**
- `201 Created` - Symbol added successfully
- `409 Conflict` - Symbol already in watchlist

**Usage Example:**
```typescript
const addToWatchlist = async (symbol: string, notes?: string) => {
  const response = await fetch('/api/v1/watchlist', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ symbol, exchange: 'NSE', notes })
  });
  
  if (response.status === 409) {
    console.log('Symbol already in watchlist');
    return null;
  }
  
  return response.json();
};
```

---

### **DELETE /api/v1/watchlist/{symbol}**

Remove a symbol from watchlist.

**Parameters:**
- `symbol` (path) - Stock symbol to remove (e.g., "RELIANCE")

**Response:** `204 No Content`

**Status Codes:**
- `204 No Content` - Symbol removed successfully
- `404 Not Found` - Symbol not in watchlist

**Usage Example:**
```typescript
const removeFromWatchlist = async (symbol: string) => {
  await fetch(`/api/v1/watchlist/${symbol}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
};
```

---

### **PATCH /api/v1/watchlist/{symbol}**

Update watchlist entry (notes or exchange).

**Parameters:**
- `symbol` (path) - Stock symbol to update

**Request Body:**
```json
{
  "notes": "Updated notes",
  "exchange": "BSE"
}
```

**Response:** Updated watchlist entry

---

### **POST /api/v1/watchlist/bulk**

Add multiple symbols to watchlist at once.

**Request Body:**
```json
{
  "symbols": ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
}
```

**Response:** Array of created watchlist entries (skips duplicates)

**Usage Example:**
```typescript
const bulkAddToWatchlist = async (symbols: string[]) => {
  const response = await fetch('/api/v1/watchlist/bulk', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ symbols })
  });
  return response.json();
};
```

---

### **DELETE /api/v1/watchlist**

Clear entire watchlist (remove all symbols).

**Response:** `204 No Content`

---

### **GET /api/v1/watchlist/{symbol}/check**

Check if a symbol is in watchlist.

**Parameters:**
- `symbol` (path) - Stock symbol to check

**Response:**
```json
{
  "symbol": "RELIANCE",
  "in_watchlist": true
}
```

---

## 🔄 Migration Strategy for Frontend

### Phase 1: Add API Integration (No Breaking Changes)

```typescript
// utils/preferences.ts
import { getAccessToken } from './auth';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000';

export const getPreferences = async () => {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE}/api/v1/preferences`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

export const updatePreferences = async (updates: Partial<Preferences>) => {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE}/api/v1/preferences`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(updates)
  });
  return response.json();
};

// utils/watchlist.ts
export const getWatchlist = async () => {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE}/api/v1/watchlist`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

export const addToWatchlist = async (symbol: string, notes?: string) => {
  const token = await getAccessToken();
  const response = await fetch(`${API_BASE}/api/v1/watchlist`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ symbol, exchange: 'NSE', notes })
  });
  
  if (response.status === 409) return null; // Already exists
  return response.json();
};

export const removeFromWatchlist = async (symbol: string) => {
  const token = await getAccessToken();
  await fetch(`${API_BASE}/api/v1/watchlist/${symbol}`, {
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  });
};
```

---

### Phase 2: Implement Fallback Strategy

```typescript
// hooks/usePreferences.ts
import { useState, useEffect } from 'react';
import { getPreferences, updatePreferences } from '../utils/preferences';

export const usePreferences = () => {
  const [preferences, setPreferences] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const loadPreferences = async () => {
      try {
        // Try API first
        const prefs = await getPreferences();
        setPreferences(prefs);
        
        // Migrate from localStorage if this is first time
        if (!prefs.disclosure_accepted) {
          const localDisclosure = localStorage.getItem('arise_disclosure_accepted_v1');
          if (localDisclosure === '1') {
            await updatePreferences({ disclosure_accepted: true });
          }
        }
      } catch (error) {
        // Fallback to localStorage
        console.warn('API failed, using localStorage', error);
        const localPrefs = {
          universe: localStorage.getItem('arise_universe') || 'NIFTY50',
          risk_profile: localStorage.getItem('arise_risk') || 'Moderate',
          // ... other fields
        };
        setPreferences(localPrefs);
      } finally {
        setLoading(false);
      }
    };
    
    loadPreferences();
  }, []);
  
  const update = async (updates: Partial<Preferences>) => {
    try {
      const updated = await updatePreferences(updates);
      setPreferences(updated);
    } catch (error) {
      // Fallback to localStorage
      console.warn('API update failed, using localStorage', error);
      Object.entries(updates).forEach(([key, value]) => {
        localStorage.setItem(`arise_${key}`, JSON.stringify(value));
      });
      setPreferences({ ...preferences, ...updates });
    }
  };
  
  return { preferences, loading, updatePreferences: update };
};
```

---

### Phase 3: One-Time Migration Script

```typescript
// utils/migrateLocalStorage.ts
export const migrateLocalStorageToBackend = async () => {
  const token = await getAccessToken();
  if (!token) return;
  
  // Check if migration already done
  const migrated = localStorage.getItem('arise_migrated_to_backend_v1');
  if (migrated === '1') return;
  
  try {
    // Migrate preferences
    const preferencesData = {
      disclosure_accepted: localStorage.getItem('arise_disclosure_accepted_v1') === '1',
      universe: localStorage.getItem('arise_universe') || 'NIFTY50',
      market_region: localStorage.getItem('arise_market_region') || 'India',
      risk_profile: localStorage.getItem('arise_risk') || 'Moderate',
      trading_modes: JSON.parse(localStorage.getItem('arise_modes') || '{}'),
      primary_mode: localStorage.getItem('arise_primary_mode') || 'Swing',
      auxiliary_modes: JSON.parse(localStorage.getItem('arise_auxiliary_modes') || '[]')
    };
    
    await updatePreferences(preferencesData);
    
    // Migrate watchlist
    const watchlistStr = localStorage.getItem('arise_watchlist');
    if (watchlistStr) {
      const symbols = JSON.parse(watchlistStr);
      if (Array.isArray(symbols) && symbols.length > 0) {
        await fetch(`${API_BASE}/api/v1/watchlist/bulk`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ symbols })
        });
      }
    }
    
    // Mark as migrated
    localStorage.setItem('arise_migrated_to_backend_v1', '1');
    console.log('✅ Successfully migrated localStorage to backend');
    
  } catch (error) {
    console.error('❌ Migration failed:', error);
  }
};

// Call this on app initialization (after login)
// In App.tsx or similar:
useEffect(() => {
  if (isAuthenticated) {
    migrateLocalStorageToBackend();
  }
}, [isAuthenticated]);
```

---

### Phase 4: Replace localStorage Calls

```typescript
// OLD CODE (App.tsx)
const [universe, setUniverse] = useState(() => {
  try { return localStorage.getItem('arise_universe') || 'NIFTY50' } 
  catch { return 'NIFTY50' }
});

const handleUniverseChange = (newUniverse: string) => {
  setUniverse(newUniverse);
  localStorage.setItem('arise_universe', newUniverse);
};

// NEW CODE (App.tsx)
const { preferences, updatePreferences } = usePreferences();
const universe = preferences?.universe || 'NIFTY50';

const handleUniverseChange = async (newUniverse: string) => {
  await updatePreferences({ universe: newUniverse });
};
```

---

## 📝 Data That Should REMAIN in localStorage

These are **session-level caches** that should NOT be migrated to backend:

```typescript
// Real-time market data (refreshed frequently)
localStorage.getItem('arise_market')
localStorage.getItem('arise_flows')
localStorage.getItem('arise_news')
localStorage.getItem('arise_spark')
localStorage.getItem('arise_picks')
localStorage.getItem('arise_winning_trades')
localStorage.getItem('arise_strategy_cache_v1')
```

**Reason:** These are temporary caches of real-time data that change frequently and don't need persistence across devices.

---

## 🧪 Testing the APIs

### Using cURL

```bash
# Get preferences
curl -X GET http://localhost:8000/api/v1/preferences \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Update preferences
curl -X PUT http://localhost:8000/api/v1/preferences \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"universe": "NIFTY500", "risk_profile": "Aggressive"}'

# Get watchlist
curl -X GET http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Add to watchlist
curl -X POST http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "RELIANCE", "exchange": "NSE"}'

# Remove from watchlist
curl -X DELETE http://localhost:8000/api/v1/watchlist/RELIANCE \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🚀 Deployment Checklist

### Backend
- [x] Create database models (UserPreferences, UserWatchlist)
- [x] Create database migrations
- [x] Run migrations on RDS
- [x] Create service layer
- [x] Create API endpoints
- [x] Register routers in main app
- [ ] Deploy to Render.com
- [ ] Test APIs in production

### Frontend
- [ ] Create API utility functions
- [ ] Create React hooks (usePreferences, useWatchlist)
- [ ] Implement fallback strategy
- [ ] Create migration script
- [ ] Test migration flow
- [ ] Replace localStorage calls
- [ ] Deploy to production
- [ ] Monitor migration success rate

---

## 🔒 Security Notes

1. **Authentication Required**: All endpoints require valid JWT token
2. **User Isolation**: Users can only access their own data (enforced by user_id from JWT)
3. **Input Validation**: All inputs validated via Pydantic schemas
4. **SQL Injection Protection**: Using SQLAlchemy ORM (parameterized queries)
5. **Rate Limiting**: Consider adding rate limiting in production

---

## 📊 Success Metrics

Track these metrics to ensure successful migration:

1. **Migration Success Rate**: % of users who successfully migrated
2. **API Response Time**: < 200ms for preferences, < 300ms for watchlist
3. **Error Rate**: < 1% of API calls should fail
4. **Data Consistency**: Compare localStorage vs backend data
5. **User Retention**: No drop in user retention post-migration

---

## 🆘 Troubleshooting

### Issue: 401 Unauthorized
**Solution**: Check JWT token is valid and not expired. Refresh token if needed.

### Issue: 409 Conflict (Watchlist)
**Solution**: Symbol already in watchlist. Use GET to check existing watchlist first.

### Issue: API slow or timing out
**Solution**: Check database connection, verify RDS is accessible, check network latency.

### Issue: Data not syncing
**Solution**: Verify user_id in JWT matches database records. Check for transaction rollbacks.

---

## 📞 Support

For backend API issues, contact backend team.  
For frontend integration issues, refer to this documentation or create a ticket.

**Backend Repository**: `/Users/adeeb/Documents/Pronttera/Fyntrix/fyntix-backend`  
**API Base URL (Prod)**: `https://fyntrix-backend-8ym9.onrender.com`  
**API Base URL (Dev)**: `http://localhost:8000`
