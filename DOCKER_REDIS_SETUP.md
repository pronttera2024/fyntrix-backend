# Docker Setup with Redis Inside Container

This guide explains how to run the Fyntrix backend with Redis embedded in the same Docker container.

## Architecture

The application now runs Redis and FastAPI in the same container:
- **Redis**: Runs on `127.0.0.1:6379` inside the container
- **FastAPI**: Runs on `0.0.0.0:$PORT` (default 8000)
- **Process Management**: Uses a bash startup script for simplicity

## Files Overview

### 1. `Dockerfile`
- Installs `redis-server` and `supervisor` packages
- Sets up environment variables for Redis connection
- Copies `start.sh` script for container startup

### 2. `start.sh`
- Starts Redis in daemon mode on `127.0.0.1:6379`
- Waits for Redis to be ready (max 30 seconds)
- Starts FastAPI application with uvicorn

### 3. `supervisord.conf` (Alternative)
- Configuration for supervisor process manager
- Can be used instead of `start.sh` if preferred
- Manages both Redis and FastAPI as separate processes

### 4. `docker-compose.yml`
- Defines the application service
- Mounts data directories for persistence
- Includes health checks

## Local Development

### Build and Run with Docker Compose

```bash
# Build the image
docker-compose build

# Start the container
docker-compose up

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

### Build and Run with Docker

```bash
# Build the image
docker build -t fyntrix-backend .

# Run the container
docker run -p 8000:8000 \
  -e DATABASE_URL=sqlite:///./fyntrix_local.db \
  -v $(pwd)/data:/app/data \
  fyntrix-backend

# Run with custom port
docker run -p 9000:9000 \
  -e PORT=9000 \
  -e DATABASE_URL=sqlite:///./fyntrix_local.db \
  fyntrix-backend
```

## Render.com Deployment

### Configuration

The Dockerfile is ready for Render.com deployment with no additional configuration needed.

**Environment Variables** (set in Render dashboard):

```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/db

# Optional (already set in Dockerfile)
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# Render provides this automatically
PORT=10000
```

### Deployment Steps

1. **Connect Repository** to Render
2. **Create Web Service**:
   - Build Command: (leave empty, uses Dockerfile)
   - Start Command: (leave empty, uses Dockerfile CMD)
3. **Set Environment Variables**:
   - `DATABASE_URL`: Your PostgreSQL connection string
4. **Deploy**: Render will build and deploy automatically

### Verify Deployment

Check logs for these messages:

```
🚀 Starting Fyntrix Backend with Redis...
📦 Configuration:
  - App Port: 10000
  - Redis: 127.0.0.1:6379/0
🔴 Starting Redis server...
⏳ Waiting for Redis to be ready...
✅ Redis is ready!
🚀 Starting FastAPI application on port 10000...
Connected to Redis at redis://127.0.0.1:6379/0
```

## Redis Configuration

### Memory Settings

Redis is configured with:
- **Max Memory**: 256MB
- **Eviction Policy**: `allkeys-lru` (removes least recently used keys)
- **Persistence**: Disabled (no RDB/AOF) for performance
- **Bind Address**: `127.0.0.1` (localhost only, secure)

### Modify Redis Settings

Edit `start.sh` to change Redis configuration:

```bash
redis-server --bind 127.0.0.1 --port 6379 \
    --maxmemory 512mb \              # Increase memory
    --maxmemory-policy allkeys-lru \
    --save "" \
    --appendonly no \
    --daemonize yes
```

## Troubleshooting

### Redis Connection Failed

**Symptom**: `Could not connect to Redis at redis://127.0.0.1:6379/0`

**Solutions**:
1. Check Redis is running: `redis-cli -h 127.0.0.1 ping`
2. Check logs: `docker logs <container-id>`
3. Verify port not in use: `netstat -tuln | grep 6379`

### Redis Out of Memory

**Symptom**: `Redis set error: OOM command not allowed`

**Solutions**:
1. Increase maxmemory in `start.sh`
2. Clear cache: `redis-cli -h 127.0.0.1 FLUSHDB`
3. Check memory usage: `redis-cli -h 127.0.0.1 INFO memory`

### Container Startup Fails

**Symptom**: Container exits immediately

**Solutions**:
1. Check logs: `docker logs <container-id>`
2. Verify `start.sh` has execute permissions
3. Test Redis manually: `redis-server --version`

### Port Already in Use

**Symptom**: `Error starting userland proxy: listen tcp4 0.0.0.0:8000: bind: address already in use`

**Solutions**:
1. Use different port: `docker run -p 9000:8000 ...`
2. Stop conflicting service: `lsof -ti:8000 | xargs kill`
3. Use docker-compose with different port mapping

## Performance Considerations

### Memory Usage

- **Redis**: ~50-256MB depending on cache size
- **FastAPI**: ~100-200MB base + data processing
- **Total**: ~200-500MB typical usage

### Optimization Tips

1. **Increase Redis Memory**: For heavy caching workloads
2. **Enable Redis Persistence**: If cache data is critical
3. **Use Separate Redis Container**: For production at scale
4. **Monitor Memory**: Use `redis-cli INFO memory`

## Alternative: Separate Redis Container

If you prefer Redis in a separate container, uncomment in `docker-compose.yml`:

```yaml
services:
  app:
    environment:
      - REDIS_HOST=redis  # Change from 127.0.0.1
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
```

Then rebuild: `docker-compose up --build`

## Testing

### Test Redis Connection

```bash
# Enter container
docker exec -it <container-id> bash

# Test Redis
redis-cli -h 127.0.0.1 ping
# Expected: PONG

# Check Redis info
redis-cli -h 127.0.0.1 INFO server

# Test cache
redis-cli -h 127.0.0.1 SET test "hello"
redis-cli -h 127.0.0.1 GET test
```

### Test API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Top picks (should use Redis cache)
curl http://localhost:8000/top-picks?universe=nifty50&mode=Swing

# Check cache status
curl http://localhost:8000/v1/cache/redis/status
```

## Migration from External Redis

If you were using external Redis (e.g., Render Redis service):

1. **No data migration needed**: Cache will rebuild automatically
2. **Remove REDIS_URL**: From environment variables
3. **Keep REDIS_HOST**: Set to `127.0.0.1`
4. **Redeploy**: Application will use container Redis

## Security Notes

- Redis binds to `127.0.0.1` only (not accessible outside container)
- No password required (secure by network isolation)
- No persistence (data lost on restart, cache rebuilds automatically)
- Suitable for cache-only workloads

## Monitoring

### Check Redis Status

```bash
# Memory usage
docker exec <container-id> redis-cli -h 127.0.0.1 INFO memory

# Key count
docker exec <container-id> redis-cli -h 127.0.0.1 DBSIZE

# Hit rate
docker exec <container-id> redis-cli -h 127.0.0.1 INFO stats | grep hits
```

### Application Logs

```bash
# View all logs
docker logs -f <container-id>

# Filter Redis logs
docker logs <container-id> 2>&1 | grep -i redis

# Filter FastAPI logs
docker logs <container-id> 2>&1 | grep -i uvicorn
```

## Summary

✅ **Benefits**:
- Single container deployment (simpler)
- No external Redis service needed (cost savings)
- Faster local development
- Automatic Redis startup

⚠️ **Considerations**:
- Cache data lost on container restart
- Limited to single container (no Redis clustering)
- Suitable for cache-only workloads

This setup is ideal for Render.com free tier and development environments.
