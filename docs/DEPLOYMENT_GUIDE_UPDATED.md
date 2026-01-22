# Fyntrix Backend - AWS ECS Deployment Guide (Updated)

Complete guide to deploy Fyntrix backend to AWS ECS on EC2 t3.large with Redis in-container.

**Last Updated**: January 20, 2026  
**Deployment Status**: ✅ Successfully deployed on EC2 t3.large with HTTPS/SSL

---

## 📋 Prerequisites

### 1. AWS CLI Configuration

```bash
# Install AWS CLI (if not installed)
brew install awscli  # macOS
# or
pip install awscli

# Configure AWS profile for Fyntrix
aws configure --profile fyntrix
# Enter:
# - AWS Access Key ID: [YOUR_AWS_ACCESS_KEY_ID]
# - AWS Secret Access Key: [YOUR_AWS_SECRET_ACCESS_KEY]
# - Default region: ap-south-1
# - Default output format: json

# Verify profile
aws sts get-caller-identity --profile fyntrix
```

**Expected Output:**
```json
{
    "Account": "563391529004",
    "UserId": "AIDAYGLGAQAWHHLEZ62KR",
    "Arn": "arn:aws:iam::563391529004:user/Admin-Pronttera"
}
```

### 2. Docker with Buildx

```bash
# Check Docker version
docker --version

# Enable buildx for multi-architecture builds
docker buildx create --name multiarch --use
docker buildx inspect --bootstrap
```

### 3. Project Configuration

- **AWS Account ID**: `563391529004`
- **AWS Region**: `ap-south-1` (Mumbai)
- **Instance Type**: `t3.large` (2 vCPU, 8GB RAM)
- **Architecture**: `x86_64` (AMD64)

---

## 🚀 Complete Deployment Process

### Step 1: Configure AWS Profile

Set the AWS profile to use for all commands:

```bash
export AWS_PROFILE=fyntrix
export AWS_ACCOUNT_ID=563391529004
export AWS_REGION=ap-south-1
```

Add these to your `~/.zshrc` or `~/.bashrc` for persistence.

---

### Step 2: Build Docker Image for x86_64 Architecture

**⚠️ CRITICAL**: Mac users (Apple Silicon/ARM64) must build for x86_64 architecture:

```bash
# Build for x86_64 (AMD64) architecture
docker buildx build \
  --platform linux/amd64 \
  -t 563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest \
  --push \
  .
```

**Why this is important:**
- Mac M1/M2/M3 use ARM64 architecture
- EC2 t3.large instances use x86_64 (AMD64) architecture
- Without `--platform linux/amd64`, you'll get `exec format error`

**Build time**: ~10-15 minutes (compiling for different architecture)

---

### Step 3: Deploy to AWS ECR

The image is automatically pushed during the build step above. To verify:

```bash
# Check image in ECR
aws ecr describe-images \
  --repository-name fyntrix-backend \
  --region ap-south-1 \
  --profile fyntrix
```

**Alternative: Use deployment script**

```bash
# This script handles ECR authentication and push
./scripts/deploy-to-ecr.sh
```

**Expected Output:**
```
✓ ECR repository ready
✓ Docker authenticated to ECR
✓ Docker image built successfully
✓ Image pushed to ECR successfully

Image URI: 563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest
```

---

### Step 4: Deploy to AWS ECS with EC2 t3.large

Use the EC2 deployment script:

```bash
./scripts/deploy-to-ecs-ec2.sh
```

**What this script does:**

1. **Creates EC2 Key Pair** (`fyntrix-key.pem`)
   - Saved to `~/.ssh/fyntrix-key.pem`
   - Used for SSH access to EC2 instance

2. **Sets up VPC and Security Groups**
   - Port 8000: Application access
   - Port 22: SSH access

3. **Creates IAM Roles**
   - `ecsInstanceRole`: Allows EC2 to run ECS tasks
   - Attaches `AmazonEC2ContainerServiceforEC2Role` policy

4. **Creates Launch Template**
   - Instance type: `t3.large`
   - AMI: Latest ECS-optimized Amazon Linux 2
   - User data: Configures ECS agent

5. **Creates Auto Scaling Group**
   - Min: 1, Max: 2, Desired: 1
   - Automatically registers with ECS cluster

6. **Creates ECS Capacity Provider**
   - Links Auto Scaling Group to ECS cluster
   - Enables managed scaling

7. **Registers Task Definition**
   - CPU: 1024 (1 vCPU)
   - Memory: 3072 MB (3 GB)
   - Network mode: `bridge` (for EC2)
   - All environment variables configured

8. **Creates ECS Service**
   - Launch type: EC2
   - Desired count: 1
   - Health checks enabled

**Deployment time**: ~5-10 minutes

---

### Step 5: Verify Deployment

```bash
# Check service status
aws ecs describe-services \
  --cluster fyntrix-cluster \
  --services fyntrix-backend-service \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'services[0].[status,runningCount,desiredCount]' \
  --output table

# Get EC2 instance details
INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names fyntrix-backend-asg \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
  --output text)

PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo "Public IP: $PUBLIC_IP"
```

**Test endpoints:**

```bash
# Health check
curl http://$PUBLIC_IP:8000/health

# API documentation
open http://$PUBLIC_IP:8000/docs

# Redis status
curl http://$PUBLIC_IP:8000/v1/redis/status

# Redis dashboard
curl http://$PUBLIC_IP:8000/v1/redis/dashboard
```

---

## 🔧 Post-Deployment Configuration

### SSH Access to EC2 Instance

```bash
# SSH into the instance
ssh -i ~/.ssh/fyntrix-key.pem ec2-user@$PUBLIC_IP

# Check Docker containers
docker ps

# View container logs
docker logs <container-id>

# Check ECS agent
sudo systemctl status ecs

# View ECS agent logs
sudo cat /var/log/ecs/ecs-agent.log
```

### Update Application Code

```bash
# 1. Build new image for x86_64
docker buildx build \
  --platform linux/amd64 \
  -t 563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest \
  --push \
  .

# 2. Force new deployment
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --force-new-deployment \
  --region ap-south-1 \
  --profile fyntrix

# 3. Wait for deployment to complete
aws ecs wait services-stable \
  --cluster fyntrix-cluster \
  --services fyntrix-backend-service \
  --region ap-south-1 \
  --profile fyntrix
```

---

## 🌐 DNS Configuration (Route 53)

### Configure Custom Domain

Set up `backend.fyntrix.ai` subdomain to point to your EC2 instance:

**Step 1: Find Hosted Zone**

```bash
# List hosted zones
aws route53 list-hosted-zones \
  --profile fyntrix \
  --query 'HostedZones[?Name==`fyntrix.ai.`]'
```

**Expected Output:**
```json
{
  "Id": "/hostedzone/Z0855289DANZGUB2HQ52",
  "Name": "fyntrix.ai."
}
```

**Step 2: Get Current EC2 Public IP**

```bash
# Get the public IP of your running instance
PUBLIC_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=fyntrix-backend-ecs" "Name=instance-state-name,Values=running" \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo "Public IP: $PUBLIC_IP"
```

**Step 3: Create A Record**

```bash
# Create DNS record pointing to EC2 instance
cat > /tmp/route53-change.json << EOF
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "backend.fyntrix.ai",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          {
            "Value": "$PUBLIC_IP"
          }
        ]
      }
    }
  ]
}
EOF

# Apply the change
aws route53 change-resource-record-sets \
  --hosted-zone-id Z0855289DANZGUB2HQ52 \
  --change-batch file:///tmp/route53-change.json \
  --profile fyntrix
```

**Step 4: Verify DNS Resolution**

```bash
# Wait for DNS propagation (usually 30-60 seconds)
sleep 30

# Test DNS resolution
dig +short backend.fyntrix.ai

# Should return: 3.110.51.214 (or your current IP)

# Test application via domain
curl http://backend.fyntrix.ai:8000/health
```

**Step 5: Update Application URLs**

Now you can access your application using the domain:

- **API**: http://backend.fyntrix.ai:8000
- **Docs**: http://backend.fyntrix.ai:8000/docs
- **Health**: http://backend.fyntrix.ai:8000/health

### Update DNS When IP Changes

If you redeploy and get a new EC2 instance with a different IP:

```bash
# Get new IP
NEW_IP=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=fyntrix-backend-ecs" "Name=instance-state-name,Values=running" \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

# Update DNS record
cat > /tmp/route53-update.json << EOF
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "backend.fyntrix.ai",
        "Type": "A",
        "TTL": 300,
        "ResourceRecords": [
          {
            "Value": "$NEW_IP"
          }
        ]
      }
    }
  ]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id Z0855289DANZGUB2HQ52 \
  --change-batch file:///tmp/route53-update.json \
  --profile fyntrix
```

### Use Elastic IP (✅ Already Configured)

**Current Setup:**
- **Elastic IP**: `13.205.69.241`
- **Allocation ID**: `eipalloc-0034d0514b3250273`
- **Associated with**: `i-0ca82c5c71c4214f9`
- **DNS Record**: `backend.fyntrix.ai` → `13.205.69.241`

**Benefits:**
- ✅ IP address never changes (even after redeployments)
- ✅ No need to update DNS after redeployments
- ✅ Cost: FREE (when associated with running instance)

**If you need to allocate a new Elastic IP:**

```bash
# Allocate Elastic IP
ALLOCATION_ID=$(aws ec2 allocate-address \
  --domain vpc \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'AllocationId' \
  --output text)

# Get instance ID
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=fyntrix-backend-ecs" "Name=instance-state-name,Values=running" \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

# Associate Elastic IP with instance
aws ec2 associate-address \
  --instance-id $INSTANCE_ID \
  --allocation-id $ALLOCATION_ID \
  --region ap-south-1 \
  --profile fyntrix

# Get the Elastic IP
ELASTIC_IP=$(aws ec2 describe-addresses \
  --allocation-ids $ALLOCATION_ID \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'Addresses[0].PublicIp' \
  --output text)

echo "Elastic IP: $ELASTIC_IP"

# Update DNS to use Elastic IP
# (Use the same route53 update command with $ELASTIC_IP)
```

---

## 🔄 Nginx Reverse Proxy (✅ Already Configured)

**Why Nginx?**
- Access application without port number (http://backend.fyntrix.ai instead of :8000)
- Better performance and caching
- SSL/TLS termination support (for HTTPS)
- Load balancing capabilities

**Current Setup:**
- **Nginx Version**: 1.28.0
- **Listening on**: Port 80 (HTTP)
- **Proxy to**: localhost:8000 (FastAPI application)
- **Configuration**: `/etc/nginx/conf.d/fyntrix-backend.conf`

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name api.fyntrix.ai;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Install Nginx on New Instance

If you deploy a new EC2 instance, install and configure nginx:

```bash
# SSH into instance
ssh -i ~/.ssh/fyntrix-key.pem ec2-user@<ELASTIC_IP>

# Install nginx
sudo amazon-linux-extras install nginx1 -y

# Create configuration
sudo tee /etc/nginx/conf.d/fyntrix-backend.conf > /dev/null << 'EOF'
server {
    listen 80;
    server_name backend.fyntrix.ai;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Start and enable nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Check status
sudo systemctl status nginx
```

### Nginx Management Commands

```bash
# Restart nginx
sudo systemctl restart nginx

# Reload configuration (no downtime)
sudo systemctl reload nginx

# Check configuration syntax
sudo nginx -t

# View nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Security Group Requirements

Ensure these ports are open in your security group:

| Port | Protocol | Purpose | CIDR |
|------|----------|---------|------|
| 80 | TCP | HTTP (Nginx) | 0.0.0.0/0 |
| 22 | TCP | SSH | 0.0.0.0/0 |
| 8000 | TCP | FastAPI (optional, for direct access) | 0.0.0.0/0 |

```bash
# Open port 80 for HTTP
aws ec2 authorize-security-group-ingress \
  --group-id <SECURITY_GROUP_ID> \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 \
  --region ap-south-1 \
  --profile fyntrix

# Open port 22 for SSH
aws ec2 authorize-security-group-ingress \
  --group-id <SECURITY_GROUP_ID> \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0 \
  --region ap-south-1 \
  --profile fyntrix
```

---

## 📊 Monitoring and Logs

### CloudWatch Logs

```bash
# Real-time logs
aws logs tail /ecs/fyntrix-backend-task \
  --follow \
  --region ap-south-1 \
  --profile fyntrix

# Last 30 minutes
aws logs tail /ecs/fyntrix-backend-task \
  --since 30m \
  --region ap-south-1 \
  --profile fyntrix

# Filter for errors
aws logs tail /ecs/fyntrix-backend-task \
  --follow \
  --filter-pattern "ERROR" \
  --region ap-south-1 \
  --profile fyntrix
```

### ECS Service Metrics

```bash
# Service status
aws ecs describe-services \
  --cluster fyntrix-cluster \
  --services fyntrix-backend-service \
  --region ap-south-1 \
  --profile fyntrix

# Task details
aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-backend-service \
  --region ap-south-1 \
  --profile fyntrix

# Container instance details
aws ecs list-container-instances \
  --cluster fyntrix-cluster \
  --region ap-south-1 \
  --profile fyntrix
```

---

## 🚨 Troubleshooting

### Issue 1: Tasks Failing with "exec format error"

**Symptom:**
```
exec /app/start.sh: exec format error
```

**Cause:** Docker image built for wrong architecture (ARM64 instead of x86_64)

**Solution:**
```bash
# Rebuild for x86_64 architecture
docker buildx build \
  --platform linux/amd64 \
  -t 563391529004.dkr.ecr.ap-south-1.amazonaws.com/fyntrix-backend:latest \
  --push \
  .

# Force new deployment
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --force-new-deployment \
  --region ap-south-1 \
  --profile fyntrix
```

### Issue 2: Tasks Not Starting

**Check task status:**
```bash
TASK_ARN=$(aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-backend-service \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'taskArns[0]' \
  --output text)

aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN \
  --region ap-south-1 \
  --profile fyntrix
```

**Common causes:**
- Insufficient memory/CPU on EC2 instance
- Port conflicts
- Health check failures
- Missing environment variables

### Issue 3: Cannot Access Application

**Check security group:**
```bash
SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=fyntrix-backend-sg" \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

aws ec2 describe-security-groups \
  --group-ids $SG_ID \
  --region ap-south-1 \
  --profile fyntrix
```

**Ensure port 8000 is open:**
```bash
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 8000 \
  --cidr 0.0.0.0/0 \
  --region ap-south-1 \
  --profile fyntrix
```

### Issue 4: Redis Not Working

**SSH into instance and check:**
```bash
ssh -i ~/.ssh/fyntrix-key.pem ec2-user@$PUBLIC_IP

# Check if Redis is running in container
docker exec <container-id> redis-cli -h 127.0.0.1 ping

# Check Redis logs
docker logs <container-id> | grep -i redis
```

### Issue 5: Database Connection Issues

**Check RDS security group:**
- Ensure EC2 security group can access RDS on port 5432
- Verify DATABASE_URL environment variable is correct

**Test connection from EC2:**
```bash
ssh -i ~/.ssh/fyntrix-key.pem ec2-user@$PUBLIC_IP

# Install PostgreSQL client
sudo yum install -y postgresql

# Test connection
psql "postgresql://fintrixAdmin:fintriX-2026@fyntrix-db.crqq2weawp2p.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require"
```

---

## 💰 Cost Breakdown

### Monthly Costs (24/7 operation)

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| **EC2 t3.large** | 2 vCPU, 8GB RAM, On-Demand | ~$60 |
| **EBS Volume** | 30GB gp3 | ~$2.40 |
| **Data Transfer** | 10GB/month | ~$1 |
| **ECR Storage** | 1GB | ~$0.10 |
| **CloudWatch Logs** | 5GB/month | ~$2.50 |
| **Total** | | **~$66/month** |

### Cost Optimization Options

1. **Use Reserved Instances**: Save up to 40% (~$36/month)
2. **Use Spot Instances**: Save up to 70% (~$18/month, but can be interrupted)
3. **Stop during off-hours**: Save 50% if only running 12 hours/day
4. **Use t3.medium**: Half the cost (~$30/month) but less resources

---

## 🔐 Security Best Practices

### Current Security Measures

✅ **Implemented:**
- Redis bound to localhost (127.0.0.1) only
- Database uses SSL (`sslmode=require`)
- ECR image scanning enabled
- IAM roles with least privilege
- Security groups restrict access

⚠️ **Recommended Improvements:**

1. **Add Application Load Balancer**
   - Enable HTTPS with SSL certificate
   - Restrict security group to ALB only

2. **Use AWS Secrets Manager**
   ```bash
   # Store database credentials
   aws secretsmanager create-secret \
     --name fyntrix/database-url \
     --secret-string "postgresql://..." \
     --region ap-south-1 \
     --profile fyntrix
   ```

3. **Enable VPC Flow Logs**
4. **Set up AWS WAF** for API protection
5. **Enable CloudTrail** for audit logging

---

## 🔄 Backup and Disaster Recovery

### Database Backups

RDS automatically creates daily backups. To create manual snapshot:

```bash
aws rds create-db-snapshot \
  --db-instance-identifier fyntrix-db \
  --db-snapshot-identifier fyntrix-db-snapshot-$(date +%Y%m%d) \
  --region ap-south-1 \
  --profile fyntrix
```

### Application State

Redis data is ephemeral (cache only). For persistent data:

1. **Enable Redis persistence** in `start.sh`:
   ```bash
   redis-server --bind 127.0.0.1 --port 6379 \
       --save 900 1 \
       --save 300 10 \
       --save 60 10000 \
       --daemonize yes
   ```

2. **Mount EBS volume** for Redis data directory

### Disaster Recovery Plan

1. **AMI Backup**: Create AMI of EC2 instance monthly
2. **Code Repository**: All code in Git (primary backup)
3. **Database**: RDS automated backups (7-day retention)
4. **Configuration**: All IaC scripts in repository

---

## 📝 Environment Variables

All environment variables are configured in `ecs-environment.json`:

| Variable | Value | Purpose |
|----------|-------|---------|
| `PORT` | 8000 | Application port |
| `DATABASE_URL` | PostgreSQL connection string | RDS database |
| `REDIS_HOST` | 127.0.0.1 | Redis in same container |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis database number |
| `AWS_COGNITO_REGION` | ap-south-1 | Cognito region |
| `AWS_COGNITO_USER_POOL_ID` | ap-south-1_k7eaenYhs | User pool |
| `AWS_COGNITO_CLIENT_ID` | avvfss72k8mt7hkhejtjnoea3 | App client |
| `AWS_COGNITO_CLIENT_SECRET` | (secret) | App client secret |
| `GOOGLE_CLIENT_ID` | (client-id) | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | (secret) | Google OAuth secret |
| `ENV_NAME` | production | Environment name |

---

## 🛠️ Management Commands

### Start/Stop Service

```bash
# Stop service (scale to 0)
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --desired-count 0 \
  --region ap-south-1 \
  --profile fyntrix

# Start service (scale to 1)
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --desired-count 1 \
  --region ap-south-1 \
  --profile fyntrix
```

### Scale Service

```bash
# Scale to 2 instances
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --desired-count 2 \
  --region ap-south-1 \
  --profile fyntrix
```

### Delete Everything

```bash
# 1. Delete ECS service
aws ecs delete-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --force \
  --region ap-south-1 \
  --profile fyntrix

# 2. Delete capacity provider
aws ecs delete-capacity-provider \
  --capacity-provider fyntrix-cp \
  --region ap-south-1 \
  --profile fyntrix

# 3. Delete Auto Scaling Group
aws autoscaling delete-auto-scaling-group \
  --auto-scaling-group-name fyntrix-backend-asg \
  --force-delete \
  --region ap-south-1 \
  --profile fyntrix

# 4. Delete Launch Template
aws ec2 delete-launch-template \
  --launch-template-name fyntrix-backend-lt \
  --region ap-south-1 \
  --profile fyntrix

# 5. Delete ECS cluster
aws ecs delete-cluster \
  --cluster fyntrix-cluster \
  --region ap-south-1 \
  --profile fyntrix

# 6. Delete ECR repository
aws ecr delete-repository \
  --repository-name fyntrix-backend \
  --force \
  --region ap-south-1 \
  --profile fyntrix

# 7. Delete security group
aws ec2 delete-security-group \
  --group-id $SG_ID \
  --region ap-south-1 \
  --profile fyntrix

# 8. Delete key pair
aws ec2 delete-key-pair \
  --key-name fyntrix-key \
  --region ap-south-1 \
  --profile fyntrix
```

---

## ✅ Deployment Checklist

- [ ] AWS CLI configured with `fyntrix` profile
- [ ] Docker buildx enabled for multi-architecture builds
- [ ] Environment variables configured in `ecs-environment.json`
- [ ] RDS database accessible from VPC
- [ ] Docker image built for x86_64 architecture
- [ ] Image pushed to ECR successfully
- [ ] ECS cluster created
- [ ] EC2 instance launched and registered with ECS
- [ ] ECS service created and stable
- [ ] Tasks running successfully (not stopped)
- [ ] Health checks passing
- [ ] Application accessible via public IP
- [ ] Redis working (test `/v1/redis/status`)
- [ ] Database connection working
- [ ] CloudWatch logs streaming
- [ ] SSH access working with key pair

---

## 📞 Quick Reference

### Current Deployment

- **AWS Account**: 563391529004
- **Region**: ap-south-1 (Mumbai)
- **Profile**: fyntrix
- **Cluster**: fyntrix-cluster
- **Service**: fyntrix-backend-service
- **Instance Type**: t3.large
- **Elastic IP**: 13.205.69.241 (static, for SSH access)
- **Domain**: api.fyntrix.ai (HTTPS enabled)
- **SSL Certificate**: AWS Certificate Manager (ACM)
- **Load Balancer**: Application Load Balancer (ALB)
- **Reverse Proxy**: Nginx (port 80 → 8000)
- **SSH Key**: ~/.ssh/fyntrix-key.pem

### Important URLs

- **Application**: https://api.fyntrix.ai (HTTPS)
- **API Docs**: https://api.fyntrix.ai/docs
- **Health Check**: https://api.fyntrix.ai/health
- **Redis Dashboard**: https://api.fyntrix.ai/v1/redis/dashboard

**HTTP Auto-Redirects to HTTPS**: http://api.fyntrix.ai → https://api.fyntrix.ai

**Alternative (Direct IP - HTTP only)**:
- http://13.205.69.241

### Quick Commands

```bash
# Set profile
export AWS_PROFILE=fyntrix

# Test application (no port needed!)
curl http://backend.fyntrix.ai/health

# Open API docs in browser
open http://backend.fyntrix.ai/docs

# Get Elastic IP
aws ec2 describe-addresses \
  --allocation-ids eipalloc-0034d0514b3250273 \
  --region ap-south-1 \
  --profile fyntrix \
  --query 'Addresses[0].PublicIp' \
  --output text

# View logs
aws logs tail /ecs/fyntrix-backend-task --follow

# SSH to instance (using Elastic IP)
ssh -i ~/.ssh/fyntrix-key.pem ec2-user@13.205.69.241

# Force redeploy
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-backend-service \
  --force-new-deployment

# Check nginx status
ssh -i ~/.ssh/fyntrix-key.pem ec2-user@13.205.69.241 'sudo systemctl status nginx'
```

---

**Last Successful Deployment**: January 19, 2026, 4:00 PM IST  
**Deployment Status**: ✅ Running on EC2 t3.large  
**Architecture**: x86_64 (AMD64)  
**Domain**: backend.fyntrix.ai  
**Elastic IP**: 13.205.69.241 (permanent)  
**Reverse Proxy**: Nginx (port 80)  
**Health Status**: Healthy  

**Access URLs (No Port Required!):**
- **Production**: http://backend.fyntrix.ai
- **API Docs**: http://backend.fyntrix.ai/docs
- **Health Check**: http://backend.fyntrix.ai/health
- **Redis Dashboard**: http://backend.fyntrix.ai/v1/redis/dashboard

**Direct IP Access:**
- http://13.205.69.241
