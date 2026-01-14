# AWS ECS Deployment Guide - Complete Setup

This guide walks you through deploying your Fyntrix FastAPI application to AWS ECS (Elastic Container Service) with Redis sidecar, from scratch to production.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [AWS Infrastructure Setup](#aws-infrastructure-setup)
3. [Build and Push Docker Image](#build-and-push-docker-image)
4. [ECS Configuration](#ecs-configuration)
5. [Deployment](#deployment)
6. [CI/CD with GitHub Actions](#cicd-with-github-actions)
7. [Monitoring and Logs](#monitoring-and-logs)
8. [Troubleshooting](#troubleshooting)

---

## 🔧 Prerequisites

### 1. AWS Account Setup

```bash
# Install AWS CLI
brew install awscli  # macOS
# or
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure AWS credentials
aws configure
# Enter:
# - AWS Access Key ID
# - AWS Secret Access Key
# - Default region (e.g., us-east-1)
# - Default output format (json)
```

### 2. Required AWS Permissions

Your IAM user/role needs these permissions:
- `AmazonEC2ContainerRegistryFullAccess`
- `AmazonECS_FullAccess`
- `IAMFullAccess` (for creating roles)
- `AmazonVPCFullAccess`
- `CloudWatchLogsFullAccess`
- `SecretsManagerReadWrite`

### 3. Tools Installation

```bash
# Docker (required)
# Download from: https://www.docker.com/products/docker-desktop

# AWS CLI Session Manager Plugin (optional, for debugging)
brew install --cask session-manager-plugin
```

---

## 🏗️ AWS Infrastructure Setup

### Step 1: Create VPC and Networking

```bash
# Create VPC
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=fyntrix-vpc}]'

# Note the VPC ID from output
export VPC_ID=vpc-xxxxx

# Create Internet Gateway
aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=fyntrix-igw}]'

export IGW_ID=igw-xxxxx

# Attach Internet Gateway to VPC
aws ec2 attach-internet-gateway \
  --vpc-id $VPC_ID \
  --internet-gateway-id $IGW_ID

# Create Public Subnets (2 for high availability)
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=fyntrix-public-subnet-1}]'

export SUBNET_1=subnet-xxxxx

aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=fyntrix-public-subnet-2}]'

export SUBNET_2=subnet-xxxxx

# Create Route Table
aws ec2 create-route-table \
  --vpc-id $VPC_ID \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=fyntrix-public-rt}]'

export RT_ID=rtb-xxxxx

# Add route to Internet Gateway
aws ec2 create-route \
  --route-table-id $RT_ID \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id $IGW_ID

# Associate subnets with route table
aws ec2 associate-route-table --subnet-id $SUBNET_1 --route-table-id $RT_ID
aws ec2 associate-route-table --subnet-id $SUBNET_2 --route-table-id $RT_ID
```

### Step 2: Create Security Groups

```bash
# Create Security Group for ECS Tasks
aws ec2 create-security-group \
  --group-name fyntrix-ecs-sg \
  --description "Security group for Fyntrix ECS tasks" \
  --vpc-id $VPC_ID

export SG_ID=sg-xxxxx

# Allow inbound HTTP traffic (port 8000)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 8000 \
  --cidr 0.0.0.0/0

# Allow outbound traffic (all)
aws ec2 authorize-security-group-egress \
  --group-id $SG_ID \
  --protocol -1 \
  --cidr 0.0.0.0/0
```

### Step 3: Create IAM Roles

```bash
# Create ECS Task Execution Role
cat > ecs-task-execution-role-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document file://ecs-task-execution-role-trust-policy.json

# Attach AWS managed policy
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Create ECS Task Role (for app permissions)
cat > ecs-task-role-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name ecsTaskRole \
  --assume-role-policy-document file://ecs-task-role-trust-policy.json

# Attach policies for Secrets Manager, S3, etc.
aws iam attach-role-policy \
  --role-name ecsTaskRole \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
```

### Step 4: Store Secrets in AWS Secrets Manager

```bash
# Store database URL
aws secretsmanager create-secret \
  --name fyntrix/database-url \
  --secret-string "postgresql://user:password@your-rds-endpoint:5432/fyntrix"

# Store Cognito credentials
aws secretsmanager create-secret \
  --name fyntrix/cognito-region \
  --secret-string "us-east-1"

aws secretsmanager create-secret \
  --name fyntrix/cognito-pool-id \
  --secret-string "us-east-1_XXXXXXXXX"

aws secretsmanager create-secret \
  --name fyntrix/cognito-client-id \
  --secret-string "your-client-id"

aws secretsmanager create-secret \
  --name fyntrix/cognito-client-secret \
  --secret-string "your-client-secret"

# Store API keys
aws secretsmanager create-secret \
  --name fyntrix/openai-api-key \
  --secret-string "sk-xxxxx"

# Get your AWS Account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Your AWS Account ID: $AWS_ACCOUNT_ID"
```

---

## 🐳 Build and Push Docker Image

### Step 1: Create ECR Repository

```bash
# Create repository
aws ecr create-repository \
  --repository-name fyntrix-app \
  --region us-east-1

# Output will show repository URI:
# YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/fyntrix-app
```

### Step 2: Build and Push Image

```bash
# Get your AWS Account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
export ECR_REPO=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/fyntrix-app

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REPO

# Build image
docker build -t fyntrix-app:latest .

# Tag image
docker tag fyntrix-app:latest $ECR_REPO:latest
docker tag fyntrix-app:latest $ECR_REPO:$(git rev-parse --short HEAD)

# Push image
docker push $ECR_REPO:latest
docker push $ECR_REPO:$(git rev-parse --short HEAD)

echo "Image pushed to: $ECR_REPO:latest"
```

---

## ⚙️ ECS Configuration

### Step 1: Create ECS Cluster

```bash
# Create Fargate cluster
aws ecs create-cluster \
  --cluster-name fyntrix-cluster \
  --capacity-providers FARGATE FARGATE_SPOT \
  --default-capacity-provider-strategy \
    capacityProvider=FARGATE,weight=1 \
    capacityProvider=FARGATE_SPOT,weight=4

# Enable Container Insights (monitoring)
aws ecs update-cluster-settings \
  --cluster fyntrix-cluster \
  --settings name=containerInsights,value=enabled
```

### Step 2: Create CloudWatch Log Groups

```bash
# Create log groups
aws logs create-log-group --log-group-name /ecs/fyntrix-app
aws logs create-log-group --log-group-name /ecs/fyntrix-redis

# Set retention (optional - 7 days)
aws logs put-retention-policy \
  --log-group-name /ecs/fyntrix-app \
  --retention-in-days 7

aws logs put-retention-policy \
  --log-group-name /ecs/fyntrix-redis \
  --retention-in-days 7
```

### Step 3: Update Task Definition

Update `ecs-task-definition.json` with your values:

```bash
# Replace placeholders in task definition
sed -i '' "s/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" ecs-task-definition.json
sed -i '' "s/us-east-1/$AWS_REGION/g" ecs-task-definition.json

# Get ARNs for IAM roles
export EXECUTION_ROLE_ARN=$(aws iam get-role --role-name ecsTaskExecutionRole --query 'Role.Arn' --output text)
export TASK_ROLE_ARN=$(aws iam get-role --role-name ecsTaskRole --query 'Role.Arn' --output text)

# Update task definition with role ARNs
sed -i '' "s|arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole|$EXECUTION_ROLE_ARN|g" ecs-task-definition.json
sed -i '' "s|arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskRole|$TASK_ROLE_ARN|g" ecs-task-definition.json
```

### Step 4: Register Task Definition

```bash
# Register task definition
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json

# Verify registration
aws ecs describe-task-definition \
  --task-definition fyntrix-app \
  --query 'taskDefinition.taskDefinitionArn'
```

---

## 🚀 Deployment

### Option 1: Deploy with ECS Service (Recommended)

```bash
# Create ECS Service
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

echo "Service deployed successfully!"
```

### Option 2: Deploy with Application Load Balancer (Production)

```bash
# Create Application Load Balancer
aws elbv2 create-load-balancer \
  --name fyntrix-alb \
  --subnets $SUBNET_1 $SUBNET_2 \
  --security-groups $SG_ID \
  --scheme internet-facing \
  --type application

export ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names fyntrix-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

# Create Target Group
aws elbv2 create-target-group \
  --name fyntrix-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3

export TG_ARN=$(aws elbv2 describe-target-groups \
  --names fyntrix-tg \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# Create Listener
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# Create ECS Service with ALB
aws ecs create-service \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service \
  --task-definition fyntrix-app \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[$SUBNET_1,$SUBNET_2],
    securityGroups=[$SG_ID],
    assignPublicIp=ENABLED
  }" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=app,containerPort=8000" \
  --health-check-grace-period-seconds 60 \
  --enable-execute-command

# Get ALB DNS name
aws elbv2 describe-load-balancers \
  --names fyntrix-alb \
  --query 'LoadBalancers[0].DNSName' \
  --output text
```

### Get Service Public IP

```bash
# Get task ARN
export TASK_ARN=$(aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service \
  --query 'taskArns[0]' \
  --output text)

# Get task details
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text

export ENI_ID=$(aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text)

# Get public IP
aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text

echo "Your app is running at: http://$(aws ec2 describe-network-interfaces --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Association.PublicIp' --output text):8000"
```

---

## 🔄 CI/CD with GitHub Actions

The GitHub Actions workflow is already created in `.github/workflows/deploy-ecs.yml`. 

### Setup GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions, and add:

```
AWS_ACCOUNT_ID: Your AWS account ID
AWS_REGION: us-east-1
AWS_ACCESS_KEY_ID: Your AWS access key
AWS_SECRET_ACCESS_KEY: Your AWS secret key
ECS_CLUSTER: fyntrix-cluster
ECS_SERVICE: fyntrix-service
```

### Trigger Deployment

```bash
# Push to main branch
git add .
git commit -m "Deploy to ECS"
git push origin main

# Or manually trigger from GitHub Actions tab
```

---

## 📊 Monitoring and Logs

### View Logs

```bash
# View app logs
aws logs tail /ecs/fyntrix-app --follow

# View Redis logs
aws logs tail /ecs/fyntrix-redis --follow

# View specific task logs
aws logs tail /ecs/fyntrix-app --follow --filter-pattern "ERROR"
```

### Monitor Service

```bash
# Get service status
aws ecs describe-services \
  --cluster fyntrix-cluster \
  --services fyntrix-service

# Get task status
aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --service-name fyntrix-service

# Get task details
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN
```

### CloudWatch Metrics

Access CloudWatch Console:
- Container Insights: ECS → Clusters → fyntrix-cluster
- Metrics: CloudWatch → Metrics → ECS
- Logs: CloudWatch → Log groups → /ecs/fyntrix-app

---

## 🔧 Updating Your Application

### Deploy New Version

```bash
# Build new image
docker build -t fyntrix-app:latest .

# Tag with version
export VERSION=$(git rev-parse --short HEAD)
docker tag fyntrix-app:latest $ECR_REPO:$VERSION
docker tag fyntrix-app:latest $ECR_REPO:latest

# Push to ECR
docker push $ECR_REPO:$VERSION
docker push $ECR_REPO:latest

# Force new deployment
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --force-new-deployment

# Wait for deployment to complete
aws ecs wait services-stable \
  --cluster fyntrix-cluster \
  --services fyntrix-service
```

### Update Task Definition

```bash
# Modify ecs-task-definition.json

# Register new version
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json

# Update service to use new task definition
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --task-definition fyntrix-app
```

---

## 🐛 Troubleshooting

### Task Fails to Start

```bash
# Check task stopped reason
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $TASK_ARN \
  --query 'tasks[0].stoppedReason'

# Check container logs
aws logs tail /ecs/fyntrix-app --since 10m
```

### Health Check Failing

```bash
# Test health endpoint
curl http://YOUR_PUBLIC_IP:8000/health

# Check target group health
aws elbv2 describe-target-health \
  --target-group-arn $TG_ARN
```

### Redis Connection Issues

```bash
# Execute command in running task
aws ecs execute-command \
  --cluster fyntrix-cluster \
  --task $TASK_ARN \
  --container app \
  --interactive \
  --command "/bin/bash"

# Inside container, test Redis
redis-cli -h localhost ping
```

### View All Task Errors

```bash
# Get stopped tasks
aws ecs list-tasks \
  --cluster fyntrix-cluster \
  --desired-status STOPPED \
  --max-results 10

# Describe stopped tasks
aws ecs describe-tasks \
  --cluster fyntrix-cluster \
  --tasks $(aws ecs list-tasks --cluster fyntrix-cluster --desired-status STOPPED --query 'taskArns[0]' --output text)
```

---

## 💰 Cost Optimization

### Use Fargate Spot

```bash
# Update service to use Fargate Spot
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --capacity-provider-strategy \
    capacityProvider=FARGATE_SPOT,weight=4,base=0 \
    capacityProvider=FARGATE,weight=1,base=1
```

### Auto Scaling

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/fyntrix-cluster/fyntrix-service \
  --min-capacity 1 \
  --max-capacity 10

# Create scaling policy (CPU-based)
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/fyntrix-cluster/fyntrix-service \
  --policy-name cpu-scaling-policy \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration \
    'PredefinedMetricSpecification={PredefinedMetricType=ECSServiceAverageCPUUtilization},TargetValue=70.0'
```

---

## 🧹 Cleanup (Delete Everything)

```bash
# Delete ECS service
aws ecs update-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --desired-count 0

aws ecs delete-service \
  --cluster fyntrix-cluster \
  --service fyntrix-service \
  --force

# Delete ECS cluster
aws ecs delete-cluster --cluster fyntrix-cluster

# Delete ALB (if created)
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
aws elbv2 delete-target-group --target-group-arn $TG_ARN

# Delete ECR repository
aws ecr delete-repository \
  --repository-name fyntrix-app \
  --force

# Delete log groups
aws logs delete-log-group --log-group-name /ecs/fyntrix-app
aws logs delete-log-group --log-group-name /ecs/fyntrix-redis

# Delete secrets
aws secretsmanager delete-secret --secret-id fyntrix/database-url --force-delete-without-recovery

# Delete security group
aws ec2 delete-security-group --group-id $SG_ID

# Delete subnets, route table, IGW, VPC
# (Follow in reverse order of creation)
```

---

## 📚 Additional Resources

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [AWS Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
- [ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [CloudWatch Container Insights](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/ContainerInsights.html)

---

## ✅ Quick Reference

```bash
# Deploy new version
./scripts/deploy-ecs.sh

# View logs
aws logs tail /ecs/fyntrix-app --follow

# Scale service
aws ecs update-service --cluster fyntrix-cluster --service fyntrix-service --desired-count 3

# Rollback
aws ecs update-service --cluster fyntrix-cluster --service fyntrix-service --task-definition fyntrix-app:PREVIOUS_VERSION
```

**Your Fyntrix app is now running on AWS ECS with Redis sidecar! 🎉**
