# Redis Setup - Quick Start

This guide shows how to run Redis **alongside** your Fyntrix application in different environments.

## 🚀 Quick Start

### Local Development with Docker

```bash
# Start everything (app + redis + postgres)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop everything
docker-compose down
```

Your app will be available at `http://localhost:8000`

### Local Development without Docker

```bash
# Install Redis
brew install redis  # macOS
# or
sudo apt-get install redis-server  # Ubuntu

# Start Redis
redis-server

# In another terminal, start your app
uvicorn app.main:app --reload

# Set REDIS_HOST=localhost in your .env file
```

---

## ☁️ Production Deployments

### AWS ECS (Elastic Container Service)

**Architecture**: Redis runs as a **sidecar container** in the same task.

```bash
# 1. Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker build -t fyntrix-app .
docker tag fyntrix-app:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/fyntrix-app:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/fyntrix-app:latest

# 2. Update ecs-task-definition.json with your account ID

# 3. Register task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json

# 4. Create/update service
aws ecs create-service --cluster fyntrix-cluster --service-name fyntrix-service --task-definition fyntrix-app --desired-count 1 --launch-type FARGATE
```

**Key Point**: Set `REDIS_HOST=localhost` in ECS (containers share network)

### Render.com

**Architecture**: Redis runs as a **private service**.

```bash
# 1. Push code to GitHub

# 2. In Render Dashboard:
#    - New → Blueprint
#    - Connect your repository
#    - Render reads render.yaml automatically

# 3. Add environment variables in Render dashboard:
#    - DATABASE_URL
#    - AWS_COGNITO_* variables
#    - API keys
```

**Key Point**: Set `REDIS_HOST=fyntrix-redis` in Render (service name)

---

## 🔧 Configuration

### Environment Variables

```env
# Docker Compose / ECS
REDIS_HOST=redis          # Docker Compose
REDIS_HOST=localhost      # ECS (sidecar)
REDIS_HOST=fyntrix-redis  # Render.com

REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=           # Empty for internal use
```

---

## ✅ Verify Redis is Working

```bash
# Check if Redis is running
docker-compose exec redis redis-cli ping
# Should return: PONG

# View cached keys
docker-compose exec redis redis-cli KEYS "*"

# Check memory usage
docker-compose exec redis redis-cli INFO memory
```

---

## 📊 Architecture Summary

| Environment | Redis Location | Connection | Network |
|-------------|---------------|------------|---------|
| **Docker Compose** | Separate container | `redis:6379` | Bridge network |
| **AWS ECS** | Sidecar container | `localhost:6379` | Shared awsvpc |
| **Render.com** | Private service | `fyntrix-redis:6379` | Private network |

**Key Principle**: Redis is **never exposed to the internet**. It only communicates with your app within the same network.

---

## 🐛 Troubleshooting

### Connection Refused

```bash
# Check REDIS_HOST environment variable
echo $REDIS_HOST

# Should be:
# - "redis" for Docker Compose
# - "localhost" for ECS
# - "fyntrix-redis" for Render
```

### Cache Not Working

```bash
# Check if Redis is healthy
docker-compose ps redis

# View Redis logs
docker-compose logs redis

# Test connection from app container
docker-compose exec app python -c "from app.services.redis_client import redis_client; print(redis_client.ping())"
```

---

## 📚 Full Documentation

See [`docs/REDIS_DEPLOYMENT_GUIDE.md`](docs/REDIS_DEPLOYMENT_GUIDE.md) for complete details.

---

## 🎯 Why This Approach?

✅ **Fast**: Redis runs in the same network as your app (localhost speed)  
✅ **Secure**: No external Redis service, no internet exposure  
✅ **Simple**: No separate Redis cluster to manage  
✅ **Scalable**: Each app instance gets its own Redis  
✅ **Cost-effective**: No additional Redis hosting fees  

Redis is **ephemeral** (in-memory only) - perfect for caching!
