#!/bin/bash
set -e

echo "🚀 Starting Fyntrix Backend with Redis..."

# Set default PORT if not provided
export PORT=${PORT:-8000}

# Ensure Redis host is localhost for container
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6379
export REDIS_DB=0

echo "📦 Configuration:"
echo "  - App Port: $PORT"
echo "  - Redis: $REDIS_HOST:$REDIS_PORT/$REDIS_DB"

# Start Redis in background
echo "🔴 Starting Redis server..."
redis-server --bind 127.0.0.1 --port 6379 \
    --maxmemory 256mb \
    --maxmemory-policy allkeys-lru \
    --save "" \
    --appendonly no \
    --daemonize yes \
    --logfile /var/log/redis.log

# Wait for Redis to be ready
echo "⏳ Waiting for Redis to be ready..."
for i in {1..30}; do
    if redis-cli -h 127.0.0.1 -p 6379 ping > /dev/null 2>&1; then
        echo "✅ Redis is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Redis failed to start after 30 seconds"
        exit 1
    fi
    sleep 1
done

# Start the FastAPI application
echo "🚀 Starting FastAPI application on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --log-level info
