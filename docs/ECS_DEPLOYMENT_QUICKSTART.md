# ECS Deployment - Quick Start Guide

This is a condensed guide to get your Fyntrix app deployed to AWS ECS quickly.

## 🚀 One-Command Setup

```bash
# 1. Setup all AWS infrastructure
./scripts/setup-ecs-infrastructure.sh

# 2. Store your secrets
aws secretsmanager create-secret --name fyntrix/database-url --secret-string "postgresql://user:pass@host:5432/db"
aws secretsmanager create-secret --name fyntrix/cognito-pool-id --secret-string "us-east-1_XXXXX"
aws secretsmanager create-secret --name fyntrix/cognito-client-id --secret-string "your-client-id"
aws secretsmanager create-secret --name fyntrix/cognito-client-secret --secret-string "your-secret"
aws secretsmanager create-secret --name fyntrix/cognito-region --secret-string "us-east-1"

# 3. Deploy your app
./scripts/deploy-ecs.sh
```

That's it! Your app will be running on ECS with Redis sidecar.

---

## 📋 Prerequisites

1. **AWS CLI installed and configured**
   ```bash
   aws configure
   ```

2. **Docker installed and running**

3. **Git repository initialized**

---

## 🔧 Step-by-Step Manual Setup

### Step 1: Setup Infrastructure (One-Time)

```bash
# Run the infrastructure setup script
./scripts/setup-ecs-infrastructure.sh

# This creates:
# - VPC with 2 public subnets
# - Internet Gateway
# - Security Groups
# - IAM Roles
# - ECR Repository
# - ECS Cluster
# - CloudWatch Log Groups
```

### Step 2: Store Secrets in AWS Secrets Manager

```bash
# Database
aws secretsmanager create-secret \
  --name fyntrix/database-url \
  --secret-string "postgresql://username:password@your-rds-endpoint:5432/fyntrix"

# Cognito
aws secretsmanager create-secret --name fyntrix/cognito-region --secret-string "us-east-1"
aws secretsmanager create-secret --name fyntrix/cognito-pool-id --secret-string "us-east-1_XXXXXXXXX"
aws secretsmanager create-secret --name fyntrix/cognito-client-id --secret-string "your-client-id"
aws secretsmanager create-secret --name fyntrix/cognito-client-secret --secret-string "your-client-secret"

# API Keys (optional)
aws secretsmanager create-secret --name fyntrix/openai-api-key --secret-string "sk-xxxxx"
```

### Step 3: Update Task Definition

```bash
# Get your AWS Account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Update task definition with your account ID
sed -i '' "s/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" ecs-task-definition.json
```

### Step 4: Register Task Definition

```bash
# Register the task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json
```

### Step 5: Create ECS Service

```bash
# Load configuration
source ecs-config.env

# Create service
aws ecs create-service \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service \
  --task-definition fyntrix-app \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[$SUBNET_1,$SUBNET_2],
    securityGroups=[$SG_ID],
    assignPublicIp=ENABLED
  }" \
  --enable-execute-command

# Wait for service to stabilize
aws ecs wait services-stable \
  --cluster fyntrix-cluster \
  --services fyntrix-service
```

### Step 6: Get Your App URL

```bash
# Get task ARN
TASK_ARN=$(aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service \
  --query 'taskArns[0]' \
  --output text)

# Get network interface ID
ENI_ID=$(aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text)

# Get public IP
PUBLIC_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text)

echo "Your app is running at: http://$PUBLIC_IP:8000"
echo "Health check: http://$PUBLIC_IP:8000/health"
```

---

## 🔄 Deploying Updates

```bash
# Simple deployment (recommended)
./scripts/deploy-ecs.sh

# Or manually:
# 1. Build and push new image
docker build -t fyntrix-app .
docker tag fyntrix-app:latest $ECR_REPO:latest
docker push $ECR_REPO:latest

# 2. Force new deployment
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --force-new-deployment
```

---

## 🤖 CI/CD with GitHub Actions

### Setup GitHub Secrets

In your GitHub repository → Settings → Secrets and variables → Actions:

```
AWS_ACCESS_KEY_ID: <your-access-key>
AWS_SECRET_ACCESS_KEY: <your-secret-key>
AWS_ACCOUNT_ID: <your-account-id>
AWS_REGION: us-east-1
```

### Automatic Deployment

Push to `main` branch:
```bash
git add .
git commit -m "Deploy to ECS"
git push origin main
```

GitHub Actions will automatically:
1. Build Docker image
2. Push to ECR
3. Update ECS service
4. Wait for deployment to stabilize

---

## 📊 Monitoring

```bash
# View logs
aws logs tail /ecs/fyntrix-app --follow

# Check service status
aws ecs describe-services \
  --cluster fyntrix-cluster \
  --services fyntrix-service

# List running tasks
aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service
```

---

## 🐛 Troubleshooting

### Task fails to start

```bash
# Check stopped tasks
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $(aws ecs list-tasks --cluster fyntrix-cluster --desired-status STOPPED --query 'taskArns[0]' --output text)

# View logs
aws logs tail /ecs/fyntrix-app --since 10m
```

### Can't access the app

```bash
# Check security group allows port 8000
aws ec2 describe-security-groups --group-ids $SG_ID

# Check task is running
aws ecs list-tasks --cluster fyntrix-cluster --service-name fyntrix-service
```

### Redis connection issues

```bash
# Execute command in running container
aws ecs execute-command \
  --cluster fyntrix-cluster \
  --task $TASK_ARN \
  --container app \
  --interactive \
  --command "/bin/bash"

# Test Redis from inside container
redis-cli -h localhost ping
```

---

## 💰 Cost Optimization

```bash
# Use Fargate Spot (70% cheaper)
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --capacity-provider-strategy \
    capacityProvider=FARGATE_SPOT,weight=4,base=0 \
    capacityProvider=FARGATE,weight=1,base=1

# Scale down when not needed
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --desired-count 0
```

---

## 🧹 Cleanup

```bash
# Delete service
aws ecs update-service --cluster fyntrix-cluster --service fyntrix-service --desired-count 0
aws ecs delete-service --cluster fyntrix-cluster --service fyntrix-service --force

# Delete cluster
aws ecs delete-cluster --cluster fyntrix-cluster

# Delete ECR repository
aws ecr delete-repository --repository-name fyntrix-app --force

# Delete other resources (VPC, subnets, etc.) manually from AWS Console
```

---

## 📚 Full Documentation

For detailed information, see:
- **[Complete ECS Deployment Guide](docs/AWS_ECS_DEPLOYMENT_GUIDE.md)** - Full step-by-step guide
- **[Redis Deployment Guide](docs/REDIS_DEPLOYMENT_GUIDE.md)** - Redis configuration details

---

## ✅ Architecture

```
┌─────────────────────────────────────────┐
│         AWS ECS Task (Fargate)          │
│                                         │
│  ┌──────────┐         ┌──────────┐    │
│  │  Redis   │◄───────►│   App    │    │
│  │  :6379   │         │  :8000   │    │
│  └──────────┘         └──────────┘    │
│                                         │
│  Communication: localhost (ultra-fast)  │
└─────────────────────────────────────────┘
              │
              ▼
        Internet Gateway
              │
              ▼
          Public IP
```

**Key Features:**
- ✅ Redis runs as sidecar (same task)
- ✅ Communication via localhost
- ✅ Auto-scaling ready
- ✅ CloudWatch monitoring
- ✅ Zero-downtime deployments

---

**Need help?** Check the full guide: `docs/AWS_ECS_DEPLOYMENT_GUIDE.md`
