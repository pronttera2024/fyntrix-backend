#!/bin/bash

# Complete Deployment Script for Fyntrix Backend
# Deploys to AWS ECR and ECS in one command

set -e

echo "🚀 Fyntrix Backend - Complete Deployment"
echo "========================================="

# Configuration
export AWS_PROFILE=fyntrix
export AWS_ACCOUNT_ID=563391529004
export AWS_REGION=ap-south-1
export ECR_REPOSITORY=fyntrix-backend
export IMAGE_TAG=latest
export CLUSTER_NAME=fyntrix-cluster
export SERVICE_NAME=fyntrix-backend-service

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "${YELLOW}Configuration:${NC}"
echo "  AWS Account: ${AWS_ACCOUNT_ID}"
echo "  AWS Region: ${AWS_REGION}"
echo "  ECR Repository: ${ECR_REPOSITORY}"
echo "  ECS Cluster: ${CLUSTER_NAME}"
echo "  ECS Service: ${SERVICE_NAME}"
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Step 1: Deploy to ECR
echo ""
echo "${YELLOW}Step 1: Deploying to ECR...${NC}"
./scripts/deploy-to-ecr.sh

if [ $? -ne 0 ]; then
    echo "${RED}✗ ECR deployment failed${NC}"
    exit 1
fi

# Step 2: Deploy to ECS
echo ""
echo "${YELLOW}Step 2: Deploying to ECS...${NC}"
./scripts/deploy-to-ecs.sh

if [ $? -ne 0 ]; then
    echo "${RED}✗ ECS deployment failed${NC}"
    exit 1
fi

echo ""
echo "${GREEN}=========================================${NC}"
echo "${GREEN}✓ Deployment completed successfully!${NC}"
echo "${GREEN}=========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Get public IP from ECS console or run:"
echo "   aws ecs list-tasks --cluster ${CLUSTER_NAME} --service-name ${SERVICE_NAME} --region ${AWS_REGION}"
echo ""
echo "2. Test the deployment:"
echo "   curl http://<PUBLIC_IP>:8000/health"
echo "   curl http://<PUBLIC_IP>:8000/docs"
echo ""
echo "3. View logs:"
echo "   aws logs tail /ecs/fyntrix-backend-task --follow --region ${AWS_REGION}"
echo ""
