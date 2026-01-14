#!/bin/bash

# Fyntrix ECS Infrastructure Setup Script
# This script sets up all AWS infrastructure needed for ECS deployment

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
VPC_CIDR="10.0.0.0/16"
SUBNET_1_CIDR="10.0.1.0/24"
SUBNET_2_CIDR="10.0.2.0/24"
AZ_1="${AWS_REGION}a"
AZ_2="${AWS_REGION}b"

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Fyntrix ECS Infrastructure Setup         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"

# Get AWS Account ID
echo -e "\n${YELLOW}📋 Getting AWS Account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Failed to get AWS Account ID. Check your AWS credentials.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ AWS Account ID: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}✅ Region: $AWS_REGION${NC}"

# Create VPC
echo -e "\n${YELLOW}🌐 Creating VPC...${NC}"
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block $VPC_CIDR \
    --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=fyntrix-vpc}]' \
    --query 'Vpc.VpcId' \
    --output text)
echo -e "${GREEN}✅ VPC created: $VPC_ID${NC}"

# Enable DNS hostnames
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames

# Create Internet Gateway
echo -e "\n${YELLOW}🌍 Creating Internet Gateway...${NC}"
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=fyntrix-igw}]' \
    --query 'InternetGateway.InternetGatewayId' \
    --output text)
echo -e "${GREEN}✅ Internet Gateway created: $IGW_ID${NC}"

# Attach Internet Gateway to VPC
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID
echo -e "${GREEN}✅ Internet Gateway attached to VPC${NC}"

# Create Subnets
echo -e "\n${YELLOW}🏗️  Creating Subnets...${NC}"
SUBNET_1=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block $SUBNET_1_CIDR \
    --availability-zone $AZ_1 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=fyntrix-public-subnet-1}]' \
    --query 'Subnet.SubnetId' \
    --output text)
echo -e "${GREEN}✅ Subnet 1 created: $SUBNET_1 ($AZ_1)${NC}"

SUBNET_2=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block $SUBNET_2_CIDR \
    --availability-zone $AZ_2 \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=fyntrix-public-subnet-2}]' \
    --query 'Subnet.SubnetId' \
    --output text)
echo -e "${GREEN}✅ Subnet 2 created: $SUBNET_2 ($AZ_2)${NC}"

# Enable auto-assign public IP
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_1 --map-public-ip-on-launch
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_2 --map-public-ip-on-launch

# Create Route Table
echo -e "\n${YELLOW}🛣️  Creating Route Table...${NC}"
RT_ID=$(aws ec2 create-route-table \
    --vpc-id $VPC_ID \
    --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=fyntrix-public-rt}]' \
    --query 'RouteTable.RouteTableId' \
    --output text)
echo -e "${GREEN}✅ Route Table created: $RT_ID${NC}"

# Add route to Internet Gateway
aws ec2 create-route \
    --route-table-id $RT_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID
echo -e "${GREEN}✅ Route to Internet Gateway added${NC}"

# Associate subnets with route table
aws ec2 associate-route-table --subnet-id $SUBNET_1 --route-table-id $RT_ID
aws ec2 associate-route-table --subnet-id $SUBNET_2 --route-table-id $RT_ID
echo -e "${GREEN}✅ Subnets associated with Route Table${NC}"

# Create Security Group
echo -e "\n${YELLOW}🔒 Creating Security Group...${NC}"
SG_ID=$(aws ec2 create-security-group \
    --group-name fyntrix-ecs-sg \
    --description "Security group for Fyntrix ECS tasks" \
    --vpc-id $VPC_ID \
    --query 'GroupId' \
    --output text)
echo -e "${GREEN}✅ Security Group created: $SG_ID${NC}"

# Add inbound rules
aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp \
    --port 8000 \
    --cidr 0.0.0.0/0
echo -e "${GREEN}✅ Inbound rule added: HTTP (8000)${NC}"

# Create IAM Roles
echo -e "\n${YELLOW}👤 Creating IAM Roles...${NC}"

# Check if roles already exist
if aws iam get-role --role-name ecsTaskExecutionRole &>/dev/null; then
    echo -e "${YELLOW}⚠️  ecsTaskExecutionRole already exists, skipping...${NC}"
else
    # Create ECS Task Execution Role
    cat > /tmp/ecs-task-execution-role-trust-policy.json <<EOF
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
        --assume-role-policy-document file:///tmp/ecs-task-execution-role-trust-policy.json \
        --output text > /dev/null

    aws iam attach-role-policy \
        --role-name ecsTaskExecutionRole \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

    echo -e "${GREEN}✅ ecsTaskExecutionRole created${NC}"
fi

if aws iam get-role --role-name ecsTaskRole &>/dev/null; then
    echo -e "${YELLOW}⚠️  ecsTaskRole already exists, skipping...${NC}"
else
    # Create ECS Task Role
    cat > /tmp/ecs-task-role-trust-policy.json <<EOF
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
        --assume-role-policy-document file:///tmp/ecs-task-role-trust-policy.json \
        --output text > /dev/null

    aws iam attach-role-policy \
        --role-name ecsTaskRole \
        --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

    echo -e "${GREEN}✅ ecsTaskRole created${NC}"
fi

# Create ECR Repository
echo -e "\n${YELLOW}📦 Creating ECR Repository...${NC}"
if aws ecr describe-repositories --repository-names fyntrix-app &>/dev/null; then
    echo -e "${YELLOW}⚠️  ECR repository already exists, skipping...${NC}"
else
    aws ecr create-repository \
        --repository-name fyntrix-app \
        --region $AWS_REGION \
        --output text > /dev/null
    echo -e "${GREEN}✅ ECR repository created: fyntrix-app${NC}"
fi

# Create ECS Cluster
echo -e "\n${YELLOW}🚀 Creating ECS Cluster...${NC}"
if aws ecs describe-clusters --clusters fyntrix-cluster --query 'clusters[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
    echo -e "${YELLOW}⚠️  ECS cluster already exists, skipping...${NC}"
else
    aws ecs create-cluster \
        --cluster-name fyntrix-cluster \
        --capacity-providers FARGATE FARGATE_SPOT \
        --default-capacity-provider-strategy \
            capacityProvider=FARGATE,weight=1 \
            capacityProvider=FARGATE_SPOT,weight=4 \
        --output text > /dev/null

    # Enable Container Insights
    aws ecs update-cluster-settings \
        --cluster fyntrix-cluster \
        --settings name=containerInsights,value=enabled \
        --output text > /dev/null

    echo -e "${GREEN}✅ ECS cluster created: fyntrix-cluster${NC}"
fi

# Create CloudWatch Log Groups
echo -e "\n${YELLOW}📝 Creating CloudWatch Log Groups...${NC}"
if aws logs describe-log-groups --log-group-name-prefix /ecs/fyntrix-app --query 'logGroups[0].logGroupName' --output text 2>/dev/null | grep -q "/ecs/fyntrix-app"; then
    echo -e "${YELLOW}⚠️  Log group /ecs/fyntrix-app already exists, skipping...${NC}"
else
    aws logs create-log-group --log-group-name /ecs/fyntrix-app
    aws logs put-retention-policy --log-group-name /ecs/fyntrix-app --retention-in-days 7
    echo -e "${GREEN}✅ Log group created: /ecs/fyntrix-app${NC}"
fi

if aws logs describe-log-groups --log-group-name-prefix /ecs/fyntrix-redis --query 'logGroups[0].logGroupName' --output text 2>/dev/null | grep -q "/ecs/fyntrix-redis"; then
    echo -e "${YELLOW}⚠️  Log group /ecs/fyntrix-redis already exists, skipping...${NC}"
else
    aws logs create-log-group --log-group-name /ecs/fyntrix-redis
    aws logs put-retention-policy --log-group-name /ecs/fyntrix-redis --retention-in-days 7
    echo -e "${GREEN}✅ Log group created: /ecs/fyntrix-redis${NC}"
fi

# Save configuration
echo -e "\n${YELLOW}💾 Saving configuration...${NC}"
cat > ecs-config.env <<EOF
# AWS ECS Configuration
# Generated on $(date)

AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID
AWS_REGION=$AWS_REGION
VPC_ID=$VPC_ID
SUBNET_1=$SUBNET_1
SUBNET_2=$SUBNET_2
SECURITY_GROUP_ID=$SG_ID
ECR_REPO=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/fyntrix-app

# Export these variables before deploying
export AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID
export AWS_REGION=$AWS_REGION
export VPC_ID=$VPC_ID
export SUBNET_1=$SUBNET_1
export SUBNET_2=$SUBNET_2
export SG_ID=$SG_ID
EOF

echo -e "${GREEN}✅ Configuration saved to ecs-config.env${NC}"

# Summary
echo -e "\n${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Infrastructure Setup Complete! 🎉         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}"

echo -e "\n${GREEN}📋 Summary:${NC}"
echo -e "  VPC ID:            $VPC_ID"
echo -e "  Subnet 1:          $SUBNET_1 ($AZ_1)"
echo -e "  Subnet 2:          $SUBNET_2 ($AZ_2)"
echo -e "  Security Group:    $SG_ID"
echo -e "  ECS Cluster:       fyntrix-cluster"
echo -e "  ECR Repository:    $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/fyntrix-app"

echo -e "\n${YELLOW}📝 Next Steps:${NC}"
echo -e "  1. Store secrets in AWS Secrets Manager:"
echo -e "     ${BLUE}aws secretsmanager create-secret --name fyntrix/database-url --secret-string 'postgresql://...'${NC}"
echo -e "     ${BLUE}aws secretsmanager create-secret --name fyntrix/cognito-pool-id --secret-string 'us-east-1_XXX'${NC}"
echo -e ""
echo -e "  2. Update ecs-task-definition.json with your account ID:"
echo -e "     ${BLUE}sed -i '' 's/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g' ecs-task-definition.json${NC}"
echo -e ""
echo -e "  3. Deploy your application:"
echo -e "     ${BLUE}./scripts/deploy-ecs.sh${NC}"
echo -e ""
echo -e "  4. Or register task definition and create service manually:"
echo -e "     ${BLUE}aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json${NC}"
echo -e "     ${BLUE}aws ecs create-service --cluster fyntrix-cluster --service-name fyntrix-service ...${NC}"
echo -e ""

# Cleanup temp files
rm -f /tmp/ecs-task-execution-role-trust-policy.json
rm -f /tmp/ecs-task-role-trust-policy.json
