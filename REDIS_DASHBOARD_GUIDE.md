# Redis Dashboard & Monitoring Guide

Complete guide to visualizing and managing your Redis cache in Fyntrix.

## 🎯 Overview

You have **3 ways** to monitor and manage Redis:

1. **Redis Commander** - Web-based GUI (easiest)
2. **FastAPI Endpoints** - REST API for programmatic access
3. **Redis CLI** - Command-line interface (advanced)

---

## 1️⃣ Redis Commander (Web GUI)

### Setup

Redis Commander is included in `docker-compose.yml` and provides a beautiful web interface.

**Start the services:**
```bash
docker-compose up -d
```

**Access the dashboard:**
```
http://localhost:8081
```

### Features

- 📊 **Visual key browser** - Browse all Redis keys in a tree structure
- 🔍 **Search and filter** - Find keys by pattern
- ✏️ **Edit values** - Modify Redis data directly
- 📈 **Real-time stats** - Memory usage, operations/sec
- 🗑️ **Delete keys** - Remove individual or bulk keys
- 📱 **Mobile friendly** - Works on phones/tablets

### Common Tasks

**View all top picks:**
1. Navigate to `top_picks:*` in the key browser
2. Click any key to see the full JSON data
3. Expand nested objects to explore

**Check cache hit rate:**
- Look at the "Stats" section
- Shows hits, misses, and hit rate percentage

**Clear specific cache:**
1. Search for pattern (e.g., `fyntrix:general:*`)
2. Select keys
3. Click "Delete"

---

## 2️⃣ FastAPI REST API

### Base URL
```
http://localhost:8000/v1/redis
```

### Endpoints

#### 📊 Dashboard Overview
```bash
GET /v1/redis/dashboard
```

**Response:**
```json
{
  "status": "connected",
  "connected": true,
  "timestamp": "2026-01-15T12:00:00Z",
  "server": {
    "version": "7.2.0",
    "uptime_days": 2.5,
    "connected_clients": 3
  },
  "memory": {
    "used": "45.2M",
    "peak": "52.1M",
    "max": "256M",
    "fragmentation_ratio": 1.05
  },
  "performance": {
    "ops_per_sec": 150,
    "total_commands": 1250000,
    "hit_rate_percent": 87.5,
    "hits": 10500,
    "misses": 1500
  },
  "keys": {
    "total": 245,
    "by_pattern": {
      "top_picks": 12,
      "fyntrix_general": 85,
      "fyntrix_scores": 42,
      "portfolio": 8,
      "dashboard": 6,
      "scalping": 15
    }
  }
}
```

#### 🔌 Connection Status
```bash
GET /v1/redis/status
```

#### 📋 List Keys
```bash
# All keys
GET /v1/redis/keys?pattern=*&limit=100

# Top picks only
GET /v1/redis/keys?pattern=top_picks:*

# Fyntrix cache
GET /v1/redis/keys?pattern=fyntrix:*
```

#### 🔍 Get Key Value
```bash
GET /v1/redis/key/top_picks:nifty50:swing
```

**Response:**
```json
{
  "status": "success",
  "key": "top_picks:nifty50:swing",
  "type": "string",
  "ttl": 3600,
  "value": {
    "universe": "NIFTY50",
    "mode": "Swing",
    "items": [...],
    "as_of": "2026-01-15T12:00:00Z"
  }
}
```

#### 🗑️ Delete Key
```bash
DELETE /v1/redis/key/top_picks:nifty50:swing
```

#### 📈 Detailed Stats
```bash
GET /v1/redis/stats
```

#### ℹ️ Server Info
```bash
# All info
GET /v1/redis/info

# Specific section
GET /v1/redis/info?section=memory
GET /v1/redis/info?section=stats
```

#### 🧹 Flush All Data (DANGEROUS!)
```bash
POST /v1/redis/flush?confirm=true
```

### Example Usage

**Python:**
```python
import requests

# Get dashboard
response = requests.get("http://localhost:8000/v1/redis/dashboard")
data = response.json()
print(f"Hit Rate: {data['performance']['hit_rate_percent']}%")

# List top picks
response = requests.get("http://localhost:8000/v1/redis/keys?pattern=top_picks:*")
keys = response.json()['keys']
for key in keys:
    print(f"{key['key']} - TTL: {key['ttl_human']}")

# Get specific pick
response = requests.get("http://localhost:8000/v1/redis/key/top_picks:nifty50:swing")
picks = response.json()['value']
print(f"Found {len(picks['items'])} picks")
```

**cURL:**
```bash
# Dashboard
curl http://localhost:8000/v1/redis/dashboard

# List keys
curl "http://localhost:8000/v1/redis/keys?pattern=top_picks:*"

# Get value
curl http://localhost:8000/v1/redis/key/top_picks:nifty50:swing

# Delete key
curl -X DELETE http://localhost:8000/v1/redis/key/old_cache_key
```

**JavaScript/Fetch:**
```javascript
// Get dashboard
const response = await fetch('http://localhost:8000/v1/redis/dashboard');
const data = await response.json();
console.log(`Memory Used: ${data.memory.used}`);
console.log(`Hit Rate: ${data.performance.hit_rate_percent}%`);

// List all top picks
const keys = await fetch('http://localhost:8000/v1/redis/keys?pattern=top_picks:*');
const keyData = await keys.json();
keyData.keys.forEach(key => {
    console.log(`${key.key} - ${key.type} - ${key.ttl_human}`);
});
```

---

## 3️⃣ Redis CLI

### Access Redis CLI

**From Docker container:**
```bash
# Enter the container
docker exec -it fyntrix-backend-app-1 bash

# Run Redis CLI
redis-cli -h 127.0.0.1 -p 6379
```

**From host (if Redis exposed):**
```bash
redis-cli -h localhost -p 6379
```

### Common Commands

```bash
# Test connection
PING
# Expected: PONG

# Get all keys
KEYS *

# Get keys by pattern
KEYS top_picks:*
KEYS fyntrix:general:*

# Get key value
GET top_picks:nifty50:swing

# Get key type
TYPE top_picks:nifty50:swing

# Get TTL
TTL top_picks:nifty50:swing

# Delete key
DEL old_cache_key

# Get database size
DBSIZE

# Get server info
INFO
INFO memory
INFO stats

# Monitor commands in real-time
MONITOR

# Get memory usage of key
MEMORY USAGE top_picks:nifty50:swing

# Flush database (DANGEROUS!)
FLUSHDB
```

---

## 📊 Key Patterns in Fyntrix

### Top Picks Cache
```
top_picks:{universe}:{mode}
```
Examples:
- `top_picks:nifty50:swing`
- `top_picks:banknifty:scalping`
- `top_picks:nifty100:intraday`

### General Cache
```
fyntrix:general:{key}
```
Examples:
- `fyntrix:general:ohlcv:RELIANCE:1d:365`
- `fyntrix:general:market_data:NIFTY50`

### Score Cache
```
fyntrix:scores:{symbol}:{metric}
```

### Portfolio Monitor
```
portfolio:monitor:{scope}:last
```
Examples:
- `portfolio:monitor:positions:last`
- `portfolio:monitor:watchlist:last`

### Dashboard Cache
```
dashboard:overview:{scope}
```
Examples:
- `dashboard:overview:intraday`
- `dashboard:overview:performance:7d`

### Scalping Monitor
```
scalping:monitor:last
```

---

## 🔍 Monitoring Best Practices

### 1. Check Health Regularly

**Via API:**
```bash
curl http://localhost:8000/v1/redis/dashboard | jq '.performance.hit_rate_percent'
```

**Target Metrics:**
- Hit Rate: > 70% (excellent), > 50% (good)
- Memory Usage: < 80% of max
- Ops/sec: Depends on load

### 2. Monitor Memory Usage

```bash
# Get memory stats
curl http://localhost:8000/v1/redis/stats | jq '.memory'
```

**Warning Signs:**
- Memory > 90% of max
- Fragmentation ratio > 1.5
- Frequent evictions

### 3. Track Cache Patterns

```bash
# Count keys by pattern
curl "http://localhost:8000/v1/redis/keys?pattern=top_picks:*" | jq '.count'
curl "http://localhost:8000/v1/redis/keys?pattern=fyntrix:*" | jq '.count'
```

### 4. Clean Up Old Data

```bash
# Find keys with no TTL
curl "http://localhost:8000/v1/redis/keys?pattern=*" | jq '.keys[] | select(.ttl == null)'

# Delete specific pattern
for key in $(redis-cli KEYS "old_pattern:*"); do
    redis-cli DEL $key
done
```

---

## 🎨 Building a Custom Dashboard

### HTML/JavaScript Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>Fyntrix Redis Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .metric { display: inline-block; margin: 10px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        .metric h3 { margin: 0 0 10px 0; color: #333; }
        .metric .value { font-size: 24px; font-weight: bold; color: #007bff; }
    </style>
</head>
<body>
    <h1>Redis Dashboard</h1>
    <div id="dashboard"></div>
    
    <script>
        async function loadDashboard() {
            const response = await fetch('http://localhost:8000/v1/redis/dashboard');
            const data = await response.json();
            
            const html = `
                <div class="metric">
                    <h3>Hit Rate</h3>
                    <div class="value">${data.performance.hit_rate_percent}%</div>
                </div>
                <div class="metric">
                    <h3>Memory Used</h3>
                    <div class="value">${data.memory.used}</div>
                </div>
                <div class="metric">
                    <h3>Total Keys</h3>
                    <div class="value">${data.keys.total}</div>
                </div>
                <div class="metric">
                    <h3>Ops/Sec</h3>
                    <div class="value">${data.performance.ops_per_sec}</div>
                </div>
            `;
            
            document.getElementById('dashboard').innerHTML = html;
        }
        
        loadDashboard();
        setInterval(loadDashboard, 5000); // Refresh every 5 seconds
    </script>
</body>
</html>
```

---

## 🚨 Troubleshooting

### Redis Not Connecting

**Check status:**
```bash
curl http://localhost:8000/v1/redis/status
```

**Solutions:**
1. Verify Redis is running: `docker ps | grep redis`
2. Check logs: `docker logs fyntrix-backend-app-1`
3. Restart container: `docker-compose restart app`

### High Memory Usage

**Check memory:**
```bash
curl http://localhost:8000/v1/redis/stats | jq '.memory'
```

**Solutions:**
1. Increase maxmemory in `start.sh`
2. Clear old cache: `curl -X POST "http://localhost:8000/v1/redis/flush?confirm=true"`
3. Set TTL on keys without expiry

### Low Hit Rate

**Check patterns:**
```bash
curl http://localhost:8000/v1/redis/stats | jq '.hit_rate_percent'
```

**Solutions:**
1. Increase cache TTL
2. Pre-warm cache with common queries
3. Review cache key patterns

### Keys Not Expiring

**Find keys without TTL:**
```bash
curl "http://localhost:8000/v1/redis/keys?pattern=*" | jq '.keys[] | select(.ttl == null)'
```

**Solution:**
```bash
# Set TTL on specific key
redis-cli EXPIRE key_name 3600
```

---

## 📱 Mobile Access

### Redis Commander on Mobile

1. Start services: `docker-compose up -d`
2. Get your local IP: `ifconfig | grep "inet "`
3. Access from phone: `http://YOUR_IP:8081`

### API Access from Mobile

Use Postman, Insomnia, or any HTTP client:
```
http://YOUR_IP:8000/v1/redis/dashboard
```

---

## 🔐 Security Notes

- Redis binds to `127.0.0.1` (localhost only)
- No password required (secure by network isolation)
- Redis Commander accessible only on local network
- For production, add authentication and SSL

---

## 📊 Performance Tips

1. **Use patterns wisely** - Avoid `KEYS *` in production
2. **Set appropriate TTLs** - Balance freshness vs memory
3. **Monitor hit rate** - Aim for > 70%
4. **Regular cleanup** - Remove stale keys
5. **Use pipelining** - Batch Redis commands when possible

---

## Summary

You now have **3 powerful tools** to manage Redis:

✅ **Redis Commander** - Visual, user-friendly web interface at `http://localhost:8081`
✅ **REST API** - Programmatic access via `/v1/redis/*` endpoints  
✅ **Redis CLI** - Direct command-line access for advanced operations

**Quick Start:**
```bash
# 1. Start services
docker-compose up -d

# 2. Open Redis Commander
open http://localhost:8081

# 3. Check API dashboard
curl http://localhost:8000/v1/redis/dashboard | jq
```

Happy caching! 🚀
