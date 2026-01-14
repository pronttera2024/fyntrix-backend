#!/bin/bash

# Fyntrix ECS Deployment Script
# This script automates the deployment of Fyntrix app to AWS ECS

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
ECR_REPO_NAME="fyntrix-app"
ECS_CLUSTER="fyntrix-cluster"
ECS_SERVICE="fyntrix-service"
TASK_FAMILY="fyntrix-app"

echo -e "${GREEN}🚀 Fyntrix ECS Deployment Script${NC}"
echo "=================================="

# Get AWS Account ID
echo -e "\n${YELLOW}📋 Getting AWS Account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Failed to get AWS Account ID. Check your AWS credentials.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ AWS Account ID: $AWS_ACCOUNT_ID${NC}"

# Set ECR repository URL
ECR_REPO="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"

# Get current git commit hash for versioning
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
echo -e "${GREEN}✅ Git commit: $GIT_COMMIT${NC}"

# Step 1: Login to ECR
echo -e "\n${YELLOW}🔐 Logging in to Amazon ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $ECR_REPO
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Successfully logged in to ECR${NC}"
else
    echo -e "${RED}❌ Failed to login to ECR${NC}"
    exit 1
fi

# Step 2: Build Docker image
echo -e "\n${YELLOW}🏗️  Building Docker image...${NC}"
docker build -t $ECR_REPO_NAME:latest .
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Docker image built successfully${NC}"
else
    echo -e "${RED}❌ Failed to build Docker image${NC}"
    exit 1
fi

# Step 3: Tag images
echo -e "\n${YELLOW}🏷️  Tagging Docker images...${NC}"
docker tag $ECR_REPO_NAME:latest $ECR_REPO:latest
docker tag $ECR_REPO_NAME:latest $ECR_REPO:$GIT_COMMIT
echo -e "${GREEN}✅ Images tagged: latest, $GIT_COMMIT${NC}"

# Step 4: Push to ECR
echo -e "\n${YELLOW}📤 Pushing images to ECR...${NC}"
docker push $ECR_REPO:latest
docker push $ECR_REPO:$GIT_COMMIT
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Images pushed to ECR${NC}"
    echo -e "   Repository: $ECR_REPO"
    echo -e "   Tags: latest, $GIT_COMMIT"
else
    echo -e "${RED}❌ Failed to push images to ECR${NC}"
    exit 1
fi

# Step 5: Update ECS service
echo -e "\n${YELLOW}🔄 Updating ECS service...${NC}"
aws ecs update-service \
    --cluster $ECS_CLUSTER \
    --service $ECS_SERVICE \
    --force-new-deployment \
    --region $AWS_REGION \
    --output json > /dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ ECS service update initiated${NC}"
else
    echo -e "${RED}❌ Failed to update ECS service${NC}"
    exit 1
fi

# Step 6: Wait for service to stabilize
echo -e "\n${YELLOW}⏳ Waiting for service to stabilize (this may take a few minutes)...${NC}"
aws ecs wait services-stable \
    --cluster $ECS_CLUSTER \
    --services $ECS_SERVICE \
    --region $AWS_REGION

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Service is stable and running${NC}"
else
    echo -e "${RED}⚠️  Service stabilization timed out or failed${NC}"
    echo -e "${YELLOW}Check the ECS console for details${NC}"
fi

# Step 7: Get service information
echo -e "\n${YELLOW}📊 Getting service information...${NC}"
TASK_ARN=$(aws ecs list-tasks \
    --cluster $ECS_CLUSTER \
    --service-name $ECS_SERVICE \
    --region $AWS_REGION \
    --query 'taskArns[0]' \
    --output text)

if [ "$TASK_ARN" != "None" ] && [ ! -z "$TASK_ARN" ]; then
    echo -e "${GREEN}✅ Task ARN: $TASK_ARN${NC}"
    
    # Get public IP if available
    ENI_ID=$(aws ecs describe-tasks \
        --cluster $ECS_CLUSTER \
        --tasks $TASK_ARN \
        --region $AWS_REGION \
        --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
        --output text)
    
    if [ ! -z "$ENI_ID" ]; then
        PUBLIC_IP=$(aws ec2 describe-network-interfaces \
            --network-interface-ids $ENI_ID \
            --region $AWS_REGION \
            --query 'NetworkInterfaces[0].Association.PublicIp' \
            --output text)
        
        if [ "$PUBLIC_IP" != "None" ] && [ ! -z "$PUBLIC_IP" ]; then
            echo -e "${GREEN}✅ Public IP: $PUBLIC_IP${NC}"
            echo -e "${GREEN}🌐 Access your app at: http://$PUBLIC_IP:8000${NC}"
            echo -e "${GREEN}🏥 Health check: http://$PUBLIC_IP:8000/health${NC}"
        fi
    fi
fi

# Summary
echo -e "\n${GREEN}=================================="
echo -e "✅ Deployment Complete!"
echo -e "==================================${NC}"
echo -e "Cluster: $ECS_CLUSTER"
echo -e "Service: $ECS_SERVICE"
echo -e "Image: $ECR_REPO:$GIT_COMMIT"
echo -e ""
echo -e "${YELLOW}📝 Next steps:${NC}"
echo -e "  - View logs: aws logs tail /ecs/fyntrix-app --follow"
echo -e "  - Check service: aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE"
echo -e "  - Scale service: aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --desired-count 2"
echo -e ""
