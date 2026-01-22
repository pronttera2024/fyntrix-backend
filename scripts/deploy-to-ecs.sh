#!/bin/bash

# Deploy Fyntrix Backend to AWS ECS
# This script creates ECS cluster, task definition, and service

set -e

echo "🚀 Deploying Fyntrix Backend to AWS ECS"
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
CLUSTER_NAME="${CLUSTER_NAME:-fyntrix-cluster}"
SERVICE_NAME="${SERVICE_NAME:-fyntrix-backend-service}"
TASK_FAMILY="${TASK_FAMILY:-fyntrix-backend-task}"
ECR_REPOSITORY="${ECR_REPOSITORY:-fyntrix-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Validate required variables
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "${RED}Error: AWS_ACCOUNT_ID is not set${NC}"
    echo "Usage: AWS_ACCOUNT_ID=123456789012 ./scripts/deploy-to-ecs.sh"
    exit 1
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo ""
echo "${YELLOW}Configuration:${NC}"
echo "  AWS Region: ${AWS_REGION}"
echo "  Cluster: ${CLUSTER_NAME}"
echo "  Service: ${SERVICE_NAME}"
echo "  Task Family: ${TASK_FAMILY}"
echo "  Image: ${ECR_URI}"
echo ""

# Step 1: Create ECS Cluster
echo "${YELLOW}Step 1: Creating ECS cluster...${NC}"
aws ecs describe-clusters --clusters ${CLUSTER_NAME} --region ${AWS_REGION} 2>/dev/null | grep -q ${CLUSTER_NAME} || \
    aws ecs create-cluster \
        --cluster-name ${CLUSTER_NAME} \
        --region ${AWS_REGION} \
        --capacity-providers FARGATE FARGATE_SPOT \
        --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1

echo "${GREEN}✓ ECS cluster ready${NC}"

# Step 2: Create CloudWatch Log Group
echo ""
echo "${YELLOW}Step 2: Creating CloudWatch log group...${NC}"
aws logs create-log-group \
    --log-group-name /ecs/${TASK_FAMILY} \
    --region ${AWS_REGION} 2>/dev/null || echo "Log group already exists"

echo "${GREEN}✓ Log group ready${NC}"

# Step 3: Create Task Execution Role (if not exists)
echo ""
echo "${YELLOW}Step 3: Setting up IAM roles...${NC}"

EXECUTION_ROLE_NAME="ecsTaskExecutionRole"
EXECUTION_ROLE_ARN=$(aws iam get-role --role-name ${EXECUTION_ROLE_NAME} --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$EXECUTION_ROLE_ARN" ]; then
    echo "Creating execution role..."
    aws iam create-role \
        --role-name ${EXECUTION_ROLE_NAME} \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'
    
    aws iam attach-role-policy \
        --role-name ${EXECUTION_ROLE_NAME} \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
    
    EXECUTION_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${EXECUTION_ROLE_NAME}"
    sleep 10  # Wait for role to propagate
fi

echo "${GREEN}✓ IAM roles ready${NC}"

# Step 4: Register Task Definition
echo ""
echo "${YELLOW}Step 4: Registering ECS task definition...${NC}"

cat > /tmp/task-definition.json <<EOF
{
  "family": "${TASK_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "${EXECUTION_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "fyntrix-backend",
      "image": "${ECR_URI}",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "PORT",
          "value": "8000"
        },
        {
          "name": "REDIS_HOST",
          "value": "127.0.0.1"
        },
        {
          "name": "REDIS_PORT",
          "value": "6379"
        },
        {
          "name": "REDIS_DB",
          "value": "0"
        },
        {
          "name": "ENV_NAME",
          "value": "production"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${TASK_FAMILY}",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
EOF

aws ecs register-task-definition \
    --cli-input-json file:///tmp/task-definition.json \
    --region ${AWS_REGION}

echo "${GREEN}✓ Task definition registered${NC}"

# Step 5: Get default VPC and subnets
echo ""
echo "${YELLOW}Step 5: Getting VPC configuration...${NC}"

VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION})
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" --query 'Subnets[*].SubnetId' --output text --region ${AWS_REGION} | tr '\t' ',')

echo "VPC ID: ${VPC_ID}"
echo "Subnets: ${SUBNET_IDS}"

# Step 6: Create Security Group
echo ""
echo "${YELLOW}Step 6: Creating security group...${NC}"

SG_NAME="fyntrix-backend-sg"
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" --query 'SecurityGroups[0].GroupId' --output text --region ${AWS_REGION} 2>/dev/null || echo "")

if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name ${SG_NAME} \
        --description "Security group for Fyntrix backend" \
        --vpc-id ${VPC_ID} \
        --region ${AWS_REGION} \
        --query 'GroupId' \
        --output text)
    
    # Allow inbound traffic on port 8000
    aws ec2 authorize-security-group-ingress \
        --group-id ${SG_ID} \
        --protocol tcp \
        --port 8000 \
        --cidr 0.0.0.0/0 \
        --region ${AWS_REGION}
fi

echo "Security Group ID: ${SG_ID}"
echo "${GREEN}✓ Security group ready${NC}"

# Step 7: Create or Update ECS Service
echo ""
echo "${YELLOW}Step 7: Creating/updating ECS service...${NC}"

# Check if service exists
SERVICE_EXISTS=$(aws ecs describe-services \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'services[0].status' \
    --output text 2>/dev/null || echo "")

if [ -z "$SERVICE_EXISTS" ] || [ "$SERVICE_EXISTS" = "INACTIVE" ] || [ "$SERVICE_EXISTS" = "None" ]; then
    # Create new service
    echo "Creating new service..."
    aws ecs create-service \
        --cluster ${CLUSTER_NAME} \
        --service-name ${SERVICE_NAME} \
        --task-definition ${TASK_FAMILY} \
        --desired-count 1 \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_IDS}],securityGroups=[${SG_ID}],assignPublicIp=ENABLED}" \
        --region ${AWS_REGION}
else
    # Update existing service
    echo "Updating existing service..."
    aws ecs update-service \
        --cluster ${CLUSTER_NAME} \
        --service ${SERVICE_NAME} \
        --task-definition ${TASK_FAMILY} \
        --force-new-deployment \
        --region ${AWS_REGION}
fi

echo "${GREEN}✓ ECS service deployed${NC}"

# Step 8: Wait for service to stabilize
echo ""
echo "${YELLOW}Step 8: Waiting for service to stabilize (this may take a few minutes)...${NC}"
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

echo "${GREEN}✓ Service is stable${NC}"

# Step 9: Get service details
echo ""
echo "${YELLOW}Step 9: Getting service details...${NC}"

TASK_ARN=$(aws ecs list-tasks \
    --cluster ${CLUSTER_NAME} \
    --service-name ${SERVICE_NAME} \
    --region ${AWS_REGION} \
    --query 'taskArns[0]' \
    --output text)

if [ ! -z "$TASK_ARN" ] && [ "$TASK_ARN" != "None" ]; then
    TASK_DETAILS=$(aws ecs describe-tasks \
        --cluster ${CLUSTER_NAME} \
        --tasks ${TASK_ARN} \
        --region ${AWS_REGION})
    
    PUBLIC_IP=$(echo $TASK_DETAILS | jq -r '.tasks[0].attachments[0].details[] | select(.name=="networkInterfaceId") | .value' | xargs -I {} aws ec2 describe-network-interfaces --network-interface-ids {} --region ${AWS_REGION} --query 'NetworkInterfaces[0].Association.PublicIp' --output text)
    
    echo ""
    echo "${GREEN}=======================================${NC}"
    echo "${GREEN}✓ Deployment completed successfully!${NC}"
    echo "${GREEN}=======================================${NC}"
    echo ""
    echo "Service URL: http://${PUBLIC_IP}:8000"
    echo "API Docs: http://${PUBLIC_IP}:8000/docs"
    echo "Health Check: http://${PUBLIC_IP}:8000/health"
    echo ""
    echo "To view logs:"
    echo "  aws logs tail /ecs/${TASK_FAMILY} --follow --region ${AWS_REGION}"
    echo ""
    echo "To stop service:"
    echo "  aws ecs update-service --cluster ${CLUSTER_NAME} --service ${SERVICE_NAME} --desired-count 0 --region ${AWS_REGION}"
    echo ""
fi
