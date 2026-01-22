#!/bin/bash

# Deploy Fyntrix Backend to AWS ECR
# This script builds, tags, and pushes the Docker image to ECR

set -e

echo "🚀 Deploying Fyntrix Backend to AWS ECR"
echo "========================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration - UPDATE THESE VALUES
export AWS_PROFILE="${AWS_PROFILE:-fyntrix}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-563391529004}"
ECR_REPOSITORY="${ECR_REPOSITORY:-fyntrix-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Validate required variables
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "${RED}Error: AWS_ACCOUNT_ID is not set${NC}"
    echo "Usage: AWS_ACCOUNT_ID=123456789012 ./scripts/deploy-to-ecr.sh"
    exit 1
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo ""
echo "${YELLOW}Configuration:${NC}"
echo "  AWS Region: ${AWS_REGION}"
echo "  AWS Account: ${AWS_ACCOUNT_ID}"
echo "  ECR Repository: ${ECR_REPOSITORY}"
echo "  Image Tag: ${IMAGE_TAG}"
echo "  Full URI: ${ECR_URI}:${IMAGE_TAG}"
echo ""

# Step 1: Check AWS CLI
echo "${YELLOW}Step 1: Checking AWS CLI...${NC}"
if ! command -v aws &> /dev/null; then
    echo "${RED}✗ AWS CLI not found. Please install it first.${NC}"
    exit 1
fi
echo "${GREEN}✓ AWS CLI found${NC}"

# Step 2: Check Docker
echo ""
echo "${YELLOW}Step 2: Checking Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo "${RED}✗ Docker not found. Please install it first.${NC}"
    exit 1
fi
echo "${GREEN}✓ Docker found${NC}"

# Step 3: Create ECR repository if it doesn't exist
echo ""
echo "${YELLOW}Step 3: Creating ECR repository (if not exists)...${NC}"
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} 2>/dev/null || \
    aws ecr create-repository \
        --repository-name ${ECR_REPOSITORY} \
        --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ ECR repository ready${NC}"
else
    echo "${RED}✗ Failed to create/verify ECR repository${NC}"
    exit 1
fi

# Step 4: Authenticate Docker to ECR
echo ""
echo "${YELLOW}Step 4: Authenticating Docker to ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ Docker authenticated to ECR${NC}"
else
    echo "${RED}✗ ECR authentication failed${NC}"
    exit 1
fi

# Step 5: Build Docker image
echo ""
echo "${YELLOW}Step 5: Building Docker image...${NC}"
docker build -t ${ECR_REPOSITORY}:${IMAGE_TAG} .

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ Docker image built successfully${NC}"
else
    echo "${RED}✗ Docker build failed${NC}"
    exit 1
fi

# Step 6: Tag image for ECR
echo ""
echo "${YELLOW}Step 6: Tagging image for ECR...${NC}"
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_URI}:$(date +%Y%m%d-%H%M%S)

echo "${GREEN}✓ Image tagged${NC}"

# Step 7: Push to ECR
echo ""
echo "${YELLOW}Step 7: Pushing image to ECR...${NC}"
docker push ${ECR_URI}:${IMAGE_TAG}
docker push ${ECR_URI}:$(date +%Y%m%d-%H%M%S)

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ Image pushed to ECR successfully${NC}"
else
    echo "${RED}✗ Failed to push image to ECR${NC}"
    exit 1
fi

# Step 8: Get image details
echo ""
echo "${YELLOW}Step 8: Verifying image in ECR...${NC}"
aws ecr describe-images \
    --repository-name ${ECR_REPOSITORY} \
    --region ${AWS_REGION} \
    --image-ids imageTag=${IMAGE_TAG}

echo ""
echo "${GREEN}=======================================${NC}"
echo "${GREEN}✓ Deployment to ECR completed!${NC}"
echo "${GREEN}=======================================${NC}"
echo ""
echo "Image URI: ${ECR_URI}:${IMAGE_TAG}"
echo ""
echo "Next steps:"
echo "1. Create ECS cluster: ./scripts/deploy-to-ecs.sh"
echo "2. Or update existing ECS service with new image"
echo ""
