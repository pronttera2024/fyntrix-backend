# Redis Deployment Guide

This guide explains how to deploy Redis as a sidecar/co-located container with your Fyntrix application across different environments.

## 🎯 Architecture Overview

Redis runs **in-memory** alongside your application container in the same network, ensuring:
- ✅ Low latency (localhost communication)
- ✅ No external network dependencies
- ✅ Data stays within your container network
- ✅ Automatic scaling with your app

---

## 🐳 Local Development with Docker Compose

### Start the Stack
```bash
docker-compose up -d
```

### Services
- **redis**: In-memory cache (port 6379)
- **postgres**: Database (port 5432) - optional
- **app**: FastAPI application (port 8000)

### Configuration
```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

### Access Redis CLI
```bash
docker-compose exec redis redis-cli
```

### View Logs
```bash
docker-compose logs -f redis
docker-compose logs -f app
```

---

## ☁️ AWS ECS Deployment

### Architecture
Redis runs as a **sidecar container** in the same ECS task as your application.

### Key Configuration
- **Network Mode**: `awsvpc` (containers share network namespace)
- **Redis Host**: `localhost` (same task, same network)
- **Memory**: 256MB for Redis, 768MB for app
- **Health Checks**: Both containers have health checks

### Deploy Steps

1. **Create ECR Repository**
```bash
aws ecr create-repository --repository-name fyntrix-app
```

2. **Build and Push Image**
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker build -t fyntrix-app .
docker tag fyntrix-app:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/fyntrix-app:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/fyntrix-app:latest
```

3. **Register Task Definition**
```bash
# Update ecs-task-definition.json with your account ID
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
```

4. **Create/Update Service**
```bash
aws ecs create-service \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service \
  --task-definition fyntrix-app \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

### ECS Task Definition Highlights
```json
{
  "containerDefinitions": [
    {
      "name": "redis",
      "image": "redis:7-alpine",
      "memory": 256,
      "portMappings": [{"containerPort": 6379}]
    },
    {
      "name": "app",
      "image": "YOUR_ECR_IMAGE",
      "memory": 768,
      "environment": [
        {"name": "REDIS_HOST", "value": "localhost"}
      ],
      "dependsOn": [
        {"containerName": "redis", "condition": "HEALTHY"}
      ]
    }
  ]
}
```

### Benefits
- ✅ Redis and app share the same network namespace
- ✅ Communication via `localhost:6379` (ultra-fast)
- ✅ Redis scales with your app automatically
- ✅ No external Redis service needed

---

## 🚀 Render.com Deployment

### Architecture
Redis runs as a **Private Service** that only your app can access.

### Configuration in `render.yaml`
```yaml
services:
  # Redis Private Service
  - type: pserv
    name: fyntrix-redis
    env: docker
    dockerfilePath: ./Dockerfile.redis
    
  # App Service
  - type: web
    name: fyntrix-backend
    env: docker
    envVars:
      - key: REDIS_HOST
        value: fyntrix-redis  # Service name
      - key: REDIS_PORT
        value: 6379
```

### Deploy Steps

1. **Connect Repository to Render**
   - Go to Render Dashboard
   - New → Blueprint
   - Connect your GitHub repository

2. **Render Reads `render.yaml`**
   - Automatically creates Redis private service
   - Creates web service with Redis connection

3. **Set Environment Variables**
   - Add secrets in Render dashboard:
     - `DATABASE_URL`
     - `AWS_COGNITO_*` variables
     - API keys

### Benefits
- ✅ Redis stays in private network
- ✅ Only your app can access it
- ✅ Automatic service discovery
- ✅ Managed by Render

---

## 🔧 Redis Configuration

### Memory Management
```bash
# Limit memory to 256MB
maxmemory 256mb

# Evict least recently used keys when memory is full
maxmemory-policy allkeys-lru
```

### In-Memory Only (No Persistence)
```bash
# Disable RDB snapshots
save ""

# Disable AOF
appendonly no
```

### Why In-Memory Only?
- ✅ **Fast**: No disk I/O overhead
- ✅ **Ephemeral**: Cache data is meant to be temporary
- ✅ **Stateless**: App can rebuild cache from source
- ✅ **Simple**: No backup/restore complexity

---

## 📊 Monitoring

### Check Redis Health
```bash
# Docker Compose
docker-compose exec redis redis-cli ping

# ECS (via AWS CLI)
aws ecs execute-command --cluster fyntrix-cluster \
  --task TASK_ID --container redis \
  --command "redis-cli ping" --interactive
```

### View Cache Stats
```bash
redis-cli INFO stats
redis-cli INFO memory
```

### Monitor Keys
```bash
redis-cli KEYS "dashboard:*"
redis-cli KEYS "portfolio:*"
redis-cli KEYS "top_picks:*"
```

---

## 🛡️ Security

### Network Isolation
- ✅ Redis is NOT exposed to the internet
- ✅ Only accessible within the container network
- ✅ No password needed (internal only)

### ECS Security Groups
```bash
# Only allow internal traffic
Inbound Rules:
- Port 6379: Source = Same Security Group
- Port 8000: Source = ALB Security Group
```

---

## 🔄 Scaling

### Vertical Scaling
Increase memory allocation in task definition:
```json
{
  "name": "redis",
  "memory": 512  // Increase from 256MB
}
```

### Horizontal Scaling
Each ECS task or Render instance gets its own Redis:
- ✅ No shared state issues
- ✅ Cache is local to each instance
- ✅ Warm-up happens independently

---

## 🐛 Troubleshooting

### Connection Refused
```bash
# Check REDIS_HOST value
echo $REDIS_HOST

# Docker Compose: should be "redis"
# ECS: should be "localhost"
# Render: should be "fyntrix-redis"
```

### Out of Memory
```bash
# Check memory usage
redis-cli INFO memory

# Increase maxmemory limit
redis-server --maxmemory 512mb
```

### Cache Miss Rate High
```bash
# Check stats
redis-cli INFO stats

# Increase TTL in application code
set_json("key", data, ex=3600)  # 1 hour
```

---

## 📝 Summary

| Environment | Redis Location | REDIS_HOST | Network |
|-------------|---------------|------------|---------|
| **Local Docker** | Separate container | `redis` | Bridge network |
| **AWS ECS** | Sidecar container | `localhost` | awsvpc (shared) |
| **Render.com** | Private service | `fyntrix-redis` | Private network |

**Key Principle**: Redis always runs **alongside** your app, never as an external service. This ensures low latency, security, and simplicity.
