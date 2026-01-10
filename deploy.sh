#!/bin/bash
# ARISE Backend Deployment Script for AWS ECS
set -e

# Configuration (Update these values)
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-YOUR_AWS_ACCOUNT_ID}"
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-arise-backend}"
ECS_CLUSTER="${ECS_CLUSTER:-arise-prod}"
ECS_SERVICE="${ECS_SERVICE:-arise-backend-service}"
IMAGE_TAG=$(date +%Y%m%d-%H%M%S)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   ARISE Backend Deployment${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

# Build Docker image
echo -e "${YELLOW}Step 1: Building Docker image...${NC}"
docker build -t $ECR_REPOSITORY:$IMAGE_TAG .
docker tag $ECR_REPOSITORY:$IMAGE_TAG $ECR_REPOSITORY:latest

echo -e "${GREEN}✓ Image built: $ECR_REPOSITORY:$IMAGE_TAG${NC}"

# Login to ECR
echo -e "${YELLOW}Step 2: Logging into AWS ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Tag for ECR
echo -e "${YELLOW}Step 3: Tagging image for ECR...${NC}"
docker tag $ECR_REPOSITORY:$IMAGE_TAG \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

docker tag $ECR_REPOSITORY:latest \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:latest

# Push to ECR
echo -e "${YELLOW}Step 4: Pushing to ECR...${NC}"
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:latest

echo -e "${GREEN}✓ Image pushed to ECR${NC}"

# Update ECS service
echo -e "${YELLOW}Step 5: Updating ECS service...${NC}"
aws ecs update-service \
  --cluster $ECS_CLUSTER \
  --service $ECS_SERVICE \
  --force-new-deployment \
  --region $AWS_REGION \
  --output text

echo -e "${GREEN}✓ ECS service update initiated${NC}"

# Wait for deployment to stabilize (optional)
echo -e "${YELLOW}Waiting for service to stabilize...${NC}"
aws ecs wait services-stable \
  --cluster $ECS_CLUSTER \
  --services $ECS_SERVICE \
  --region $AWS_REGION

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Image Tag: $IMAGE_TAG"
echo -e "ECR Repository: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY"
echo -e "ECS Cluster: $ECS_CLUSTER"
echo -e "ECS Service: $ECS_SERVICE"
