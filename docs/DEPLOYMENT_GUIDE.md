# Fyntrix Backend - AWS ECS Deployment Guide

Complete guide to deploy Fyntrix backend to AWS ECS with Redis in-container.

## 📋 Prerequisites

1. **AWS CLI installed and configured**
   ```bash
   aws configure
   # Enter your credentials when prompted
   ```

2. **Docker installed and running**
   ```bash
   docker --version
   ```

3. **AWS Account ID**: `563391529004`
4. **AWS Region**: `ap-south-1` (Mumbai)

---

## 🚀 Deployment Steps

### Step 1: Test Docker Container Locally

Before deploying to AWS, test the container locally:

```bash
# Build the image
docker build -t fyntrix-backend:test .

# Run the container
docker run -d \
  --name fyntrix-backend-test \
  -p 9000:8000 \
  -e DATABASE_URL="postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require" \
  -e REDIS_HOST="127.0.0.1" \
  -e REDIS_PORT="6379" \
  fyntrix-backend:test

# Wait 30 seconds for startup
sleep 30

# Test health endpoint
curl http://localhost:9000/health

# Test Redis
docker exec fyntrix-backend-test redis-cli -h 127.0.0.1 ping

# View logs
docker logs fyntrix-backend-test

# Stop and remove
docker stop fyntrix-backend-test
docker rm fyntrix-backend-test
```

**Expected Output:**
- Health endpoint returns `{"status":"ok"}`
- Redis responds with `PONG`
- Logs show "Application startup complete"

---

### Step 2: Deploy to AWS ECR

Push the Docker image to AWS Elastic Container Registry:

```bash
# Set environment variables
export AWS_ACCOUNT_ID=563391529004
export AWS_REGION=ap-south-1

# Run deployment script
./scripts/deploy-to-ecr.sh
```

**What this does:**
1. Creates ECR repository `fyntrix-backend` (if not exists)
2. Authenticates Docker to ECR
3. Builds Docker image
4. Tags image with `latest` and timestamp
5. Pushes to ECR

**Expected Output:**
```
✓ ECR repository ready
✓ Docker authenticated to ECR
✓ Docker image built successfully
✓ Image tagged
✓ Image pushed to ECR successfully

Image URI: 563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest
```

---

### Step 3: Deploy to AWS ECS

Deploy the container to ECS Fargate:

```bash
# Set environment variables
export AWS_ACCOUNT_ID=563391529004
export AWS_REGION=ap-south-1

# Run deployment script
./scripts/deploy-to-ecs.sh
```

**What this does:**
1. Creates ECS cluster `fyntrix-cluster`
2. Creates CloudWatch log group
3. Sets up IAM roles
4. Registers ECS task definition with environment variables
5. Creates security group (allows port 8000)
6. Creates/updates ECS service
7. Waits for service to stabilize

**Expected Output:**
```
✓ ECS cluster ready
✓ Log group ready
✓ IAM roles ready
✓ Task definition registered
✓ Security group ready
✓ ECS service deployed
✓ Service is stable

Service URL: http://13.232.XXX.XXX:8000
API Docs: http://13.232.XXX.XXX:8000/docs
Health Check: http://13.232.XXX.XXX:8000/health
```

---

## 🔧 Manual Deployment (Alternative)

If you prefer manual control:

### 1. Create ECR Repository

```bash
aws ecr create-repository \
  --repository-name fyntrix-backend \
  --region ap-south-1 \
  --image-scanning-configuration scanOnPush=true
```

### 2. Build and Push Image

```bash
# Login to ECR
aws ecr get-login-password --region ap-south-1 | \
  docker login --username AWS --password-stdin 563391529004.dkr.ecr.ap-south-1.amazonaws.com

# Build image
docker build -t fyntrix-backend:latest .

# Tag for ECR
docker tag fyntrix-backend:latest \
  563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest

# Push to ECR
docker push 563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest
```

### 3. Create ECS Cluster

```bash
aws ecs create-cluster \
  --cluster-name fyntrix-cluster \
  --region ap-south-1 \
  --capacity-providers FARGATE FARGATE_SPOT
```

### 4. Register Task Definition

The task definition is created automatically by the script, but you can also create it manually using the AWS Console:

- **Family**: `fyntrix-backend-task`
- **Launch Type**: Fargate
- **CPU**: 512 (.5 vCPU)
- **Memory**: 1024 (1 GB)
- **Container Port**: 8000
- **Environment Variables**: See `ecs-environment.json`

### 5. Create ECS Service

```bash
aws ecs create-service \
  --cluster fyntrix-cluster \
  --service-name fyntrix-backend-service \
  --task-definition fyntrix-backend-task \
  --desired-count 1 \
  --launch-type FARGATE \
  --region ap-south-1
```

---

## 🔍 Verification

### Check Service Status

```bash
aws ecs describe-services \
  --cluster fyntrix-cluster \
  --services fyntrix-backend-service \
  --region ap-south-1
```

### View Logs

```bash
# Real-time logs
aws logs tail /ecs/fyntrix-backend-task --follow --region ap-south-1

# Last 100 lines
aws logs tail /ecs/fyntrix-backend-task --since 10m --region ap-south-1
```

### Get Public IP

```bash
# Get task ARN
TASK_ARN=$(aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-backend-service \
  --region ap-south-1 \
  --query 'taskArns[0]' \
  --output text)

# Get task details
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN \
  --region ap-south-1 \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text | xargs -I {} \
  aws ec2 describe-network-interfaces \
  --network-interface-ids {} \
  --region ap-south-1 \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text
```

### Test Endpoints

```bash
PUBLIC_IP=<your-public-ip>

# Health check
curl http://$PUBLIC_IP:8000/health

# API docs
curl http://$PUBLIC_IP:8000/docs

# Redis status
curl http://$PUBLIC_IP:8000/v1/redis/status

# Redis dashboard
curl http://$PUBLIC_IP:8000/v1/redis/dashboard
```

---

## 📊 Environment Variables

All environment variables are configured in `ecs-environment.json`:

| Variable | Value | Description |
|----------|-------|-------------|
| `DATABASE_URL` | RDS PostgreSQL | Database connection string |
| `REDIS_HOST` | `127.0.0.1` | Redis runs in same container |
| `REDIS_PORT` | `6379` | Redis port |
| `AWS_COGNITO_*` | Cognito config | Authentication |
| `GOOGLE_CLIENT_*` | OAuth config | Google sign-in |
| `PORT` | `8000` | Application port |

---

## 🔐 Security Considerations

### Current Setup
- ✅ Redis bound to localhost (127.0.0.1) - secure
- ✅ Database uses SSL (`sslmode=require`)
- ✅ ECR image scanning enabled
- ⚠️ Port 8000 exposed to internet (0.0.0.0/0)

### Recommended Improvements

1. **Add Application Load Balancer (ALB)**
   ```bash
   # Create ALB
   # Configure HTTPS with SSL certificate
   # Restrict security group to ALB only
   ```

2. **Use AWS Secrets Manager**
   ```bash
   # Store sensitive credentials
   aws secretsmanager create-secret \
     --name fyntrix/database-url \
     --secret-string "postgresql://..."
   
   # Update task definition to use secrets
   ```

3. **Enable VPC Endpoints**
   - ECR VPC endpoint
   - CloudWatch Logs VPC endpoint
   - Secrets Manager VPC endpoint

4. **Configure Auto Scaling**
   ```bash
   aws application-autoscaling register-scalable-target \
     --service-namespace ecs \
     --scalable-dimension ecs:service:DesiredCount \
     --resource-id service/fyntrix-cluster/fyntrix-backend-service \
     --min-capacity 1 \
     --max-capacity 4
   ```

---

## 🛠️ Troubleshooting

### Container Won't Start

**Check logs:**
```bash
aws logs tail /ecs/fyntrix-backend-task --since 30m --region ap-south-1
```

**Common issues:**
- Database connection failed → Check RDS security group
- Redis not starting → Check container logs for Redis errors
- Port conflict → Ensure port 8000 is available

### Task Keeps Stopping

**Check task stopped reason:**
```bash
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks <task-arn> \
  --region ap-south-1 \
  --query 'tasks[0].stoppedReason'
```

**Common reasons:**
- Health check failing → Verify `/health` endpoint
- Out of memory → Increase task memory
- Essential container exited → Check application logs

### Can't Access Service

**Verify security group:**
```bash
# Get security group ID
SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=fyntrix-backend-sg" \
  --region ap-south-1 \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

# Check inbound rules
aws ec2 describe-security-groups \
  --group-ids $SG_ID \
  --region ap-south-1
```

**Ensure port 8000 is allowed:**
```bash
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 8000 \
  --cidr 0.0.0.0/0 \
  --region ap-south-1
```

---

## 📈 Monitoring

### CloudWatch Metrics

View in AWS Console:
- ECS → Clusters → fyntrix-cluster → Metrics
- CloudWatch → Log groups → /ecs/fyntrix-backend-task

### Key Metrics to Monitor

- **CPU Utilization** - Should be < 70%
- **Memory Utilization** - Should be < 80%
- **Task Count** - Should match desired count
- **Health Check Status** - Should be healthy

### Set Up Alarms

```bash
# CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name fyntrix-high-cpu \
  --alarm-description "Alert when CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2
```

---

## 🔄 Updates and Rollbacks

### Deploy New Version

```bash
# Build and push new image
./scripts/deploy-to-ecr.sh

# Force new deployment
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --force-new-deployment \
  --region ap-south-1
```

### Rollback to Previous Version

```bash
# List previous task definitions
aws ecs list-task-definitions \
  --family-prefix fyntrix-backend-task \
  --region ap-south-1

# Update service to use previous version
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --task-definition fyntrix-backend-task:1 \
  --region ap-south-1
```

---

## 💰 Cost Estimation

**Monthly costs (approximate):**

| Service | Configuration | Cost |
|---------|--------------|------|
| ECS Fargate | 0.5 vCPU, 1GB RAM, 24/7 | ~$15/month |
| ECR Storage | 1GB image storage | ~$0.10/month |
| CloudWatch Logs | 5GB logs/month | ~$2.50/month |
| Data Transfer | 10GB/month | ~$1/month |
| **Total** | | **~$19/month** |

**Cost optimization:**
- Use Fargate Spot for non-production (70% cheaper)
- Enable log retention (delete old logs)
- Use smaller instance if possible

---

## 🎯 Quick Reference

### Start/Stop Service

```bash
# Stop service (set desired count to 0)
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --desired-count 0 \
  --region ap-south-1

# Start service (set desired count to 1)
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --desired-count 1 \
  --region ap-south-1
```

### Delete Everything

```bash
# Delete service
aws ecs delete-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --force \
  --region ap-south-1

# Delete cluster
aws ecs delete-cluster \
  --cluster fyntrix-cluster \
  --region ap-south-1

# Delete ECR repository
aws ecr delete-repository \
  --repository-name fyntrix-backend \
  --force \
  --region ap-south-1
```

---

## 📞 Support

For issues or questions:
1. Check CloudWatch logs first
2. Review this troubleshooting guide
3. Check AWS ECS documentation
4. Contact DevOps team

---

## ✅ Deployment Checklist

- [ ] Docker image builds successfully locally
- [ ] Container runs and passes health checks locally
- [ ] Redis connectivity verified locally
- [ ] AWS CLI configured with correct credentials
- [ ] ECR repository created
- [ ] Image pushed to ECR
- [ ] ECS cluster created
- [ ] Task definition registered with all environment variables
- [ ] Security group configured
- [ ] ECS service created and stable
- [ ] Public IP obtained
- [ ] Health endpoint accessible
- [ ] API documentation accessible
- [ ] Redis dashboard accessible
- [ ] CloudWatch logs streaming
- [ ] Monitoring alarms configured

---

**Deployment Date**: January 19, 2026  
**Version**: 1.0.0  
**AWS Account**: 563391529004  
**Region**: ap-south-1 (Mumbai)
