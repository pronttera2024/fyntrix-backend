#!/bin/bash

# Deploy Fyntrix Backend to AWS ECS with EC2 (t3.large)
# This script creates ECS cluster with EC2 instances

set -e

echo "🚀 Deploying Fyntrix Backend to AWS ECS (EC2 t3.large)"
echo "======================================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
export AWS_PROFILE="${AWS_PROFILE:-fyntrix}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-563391529004}"
CLUSTER_NAME="${CLUSTER_NAME:-fyntrix-cluster}"
SERVICE_NAME="${SERVICE_NAME:-fyntrix-backend-service}"
TASK_FAMILY="${TASK_FAMILY:-fyntrix-backend-task}"
ECR_REPOSITORY="${ECR_REPOSITORY:-fyntrix-backend}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
INSTANCE_TYPE="t3.large"
KEY_NAME="${KEY_NAME:-fyntrix-key}"

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}:${IMAGE_TAG}"

echo ""
echo "${YELLOW}Configuration:${NC}"
echo "  AWS Region: ${AWS_REGION}"
echo "  Cluster: ${CLUSTER_NAME}"
echo "  Service: ${SERVICE_NAME}"
echo "  Instance Type: ${INSTANCE_TYPE}"
echo "  Image: ${ECR_URI}"
echo ""

# Step 1: Create Key Pair (if not exists)
echo "${YELLOW}Step 1: Creating EC2 key pair...${NC}"
if ! aws ec2 describe-key-pairs --key-names ${KEY_NAME} --region ${AWS_REGION} 2>/dev/null; then
    aws ec2 create-key-pair \
        --key-name ${KEY_NAME} \
        --region ${AWS_REGION} \
        --query 'KeyMaterial' \
        --output text > ~/.ssh/${KEY_NAME}.pem
    chmod 400 ~/.ssh/${KEY_NAME}.pem
    echo "${GREEN}✓ Key pair created: ~/.ssh/${KEY_NAME}.pem${NC}"
else
    echo "${GREEN}✓ Key pair already exists${NC}"
fi

# Step 2: Get VPC and Subnets
echo ""
echo "${YELLOW}Step 2: Getting VPC configuration...${NC}"
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text --region ${AWS_REGION})
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" --query 'Subnets[*].SubnetId' --output text --region ${AWS_REGION} | tr '\t' ',')
SUBNET_ID=$(echo $SUBNET_IDS | cut -d',' -f1)

echo "VPC ID: ${VPC_ID}"
echo "Subnet: ${SUBNET_ID}"

# Step 3: Create/Update Security Group
echo ""
echo "${YELLOW}Step 3: Creating security group...${NC}"
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
    
    # Allow SSH
    aws ec2 authorize-security-group-ingress \
        --group-id ${SG_ID} \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 \
        --region ${AWS_REGION}
fi

echo "Security Group ID: ${SG_ID}"
echo "${GREEN}✓ Security group ready${NC}"

# Step 4: Create IAM Role for ECS Instances
echo ""
echo "${YELLOW}Step 4: Creating IAM role for ECS instances...${NC}"
INSTANCE_ROLE_NAME="ecsInstanceRole"
INSTANCE_ROLE_ARN=$(aws iam get-role --role-name ${INSTANCE_ROLE_NAME} --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$INSTANCE_ROLE_ARN" ]; then
    aws iam create-role \
        --role-name ${INSTANCE_ROLE_NAME} \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }'
    
    aws iam attach-role-policy \
        --role-name ${INSTANCE_ROLE_NAME} \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role
    
    # Create instance profile
    aws iam create-instance-profile --instance-profile-name ${INSTANCE_ROLE_NAME}
    aws iam add-role-to-instance-profile --instance-profile-name ${INSTANCE_ROLE_NAME} --role-name ${INSTANCE_ROLE_NAME}
    
    INSTANCE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${INSTANCE_ROLE_NAME}"
    sleep 10
fi

echo "${GREEN}✓ IAM role ready${NC}"

# Step 5: Create Launch Template
echo ""
echo "${YELLOW}Step 5: Creating launch template...${NC}"

# Get latest ECS-optimized AMI
AMI_ID=$(aws ssm get-parameters \
    --names /aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id \
    --region ${AWS_REGION} \
    --query 'Parameters[0].Value' \
    --output text)

echo "ECS-Optimized AMI: ${AMI_ID}"

# Create user data script
cat > /tmp/ecs-user-data.sh <<EOF
#!/bin/bash
echo ECS_CLUSTER=${CLUSTER_NAME} >> /etc/ecs/ecs.config
echo ECS_ENABLE_TASK_IAM_ROLE=true >> /etc/ecs/ecs.config
echo ECS_ENABLE_TASK_IAM_ROLE_NETWORK_HOST=true >> /etc/ecs/ecs.config
EOF

USER_DATA=$(base64 -i /tmp/ecs-user-data.sh)

# Create launch template
LAUNCH_TEMPLATE_NAME="fyntrix-backend-lt"
aws ec2 create-launch-template \
    --launch-template-name ${LAUNCH_TEMPLATE_NAME} \
    --version-description "Fyntrix Backend ECS Instance" \
    --launch-template-data "{
        \"ImageId\": \"${AMI_ID}\",
        \"InstanceType\": \"${INSTANCE_TYPE}\",
        \"KeyName\": \"${KEY_NAME}\",
        \"IamInstanceProfile\": {
            \"Name\": \"${INSTANCE_ROLE_NAME}\"
        },
        \"SecurityGroupIds\": [\"${SG_ID}\"],
        \"UserData\": \"${USER_DATA}\",
        \"TagSpecifications\": [{
            \"ResourceType\": \"instance\",
            \"Tags\": [{
                \"Key\": \"Name\",
                \"Value\": \"fyntrix-backend-ecs\"
            }]
        }]
    }" \
    --region ${AWS_REGION} 2>/dev/null || echo "Launch template may already exist"

echo "${GREEN}✓ Launch template ready${NC}"

# Step 6: Create Auto Scaling Group
echo ""
echo "${YELLOW}Step 6: Creating Auto Scaling Group...${NC}"
ASG_NAME="fyntrix-backend-asg"

aws autoscaling create-auto-scaling-group \
    --auto-scaling-group-name ${ASG_NAME} \
    --launch-template "LaunchTemplateName=${LAUNCH_TEMPLATE_NAME}" \
    --min-size 1 \
    --max-size 2 \
    --desired-capacity 1 \
    --vpc-zone-identifier ${SUBNET_ID} \
    --region ${AWS_REGION} \
    --tags "Key=Name,Value=fyntrix-backend-ecs,PropagateAtLaunch=true" 2>/dev/null || echo "ASG may already exist"

echo "${GREEN}✓ Auto Scaling Group ready${NC}"

# Step 7: Create Capacity Provider
echo ""
echo "${YELLOW}Step 7: Creating ECS capacity provider...${NC}"
CAPACITY_PROVIDER_NAME="fyntrix-cp"

aws ecs create-capacity-provider \
    --name ${CAPACITY_PROVIDER_NAME} \
    --auto-scaling-group-provider "autoScalingGroupArn=arn:aws:autoscaling:${AWS_REGION}:${AWS_ACCOUNT_ID}:autoScalingGroup:*:autoScalingGroupName/${ASG_NAME},managedScaling={status=ENABLED,targetCapacity=80,minimumScalingStepSize=1,maximumScalingStepSize=2},managedTerminationProtection=DISABLED" \
    --region ${AWS_REGION} 2>/dev/null || echo "Capacity provider may already exist"

# Associate capacity provider with cluster
aws ecs put-cluster-capacity-providers \
    --cluster ${CLUSTER_NAME} \
    --capacity-providers ${CAPACITY_PROVIDER_NAME} \
    --default-capacity-provider-strategy capacityProvider=${CAPACITY_PROVIDER_NAME},weight=1 \
    --region ${AWS_REGION}

echo "${GREEN}✓ Capacity provider ready${NC}"

# Step 8: Wait for EC2 instance to register
echo ""
echo "${YELLOW}Step 8: Waiting for EC2 instance to register with ECS...${NC}"
sleep 30

CONTAINER_INSTANCES=$(aws ecs list-container-instances --cluster ${CLUSTER_NAME} --region ${AWS_REGION} --query 'containerInstanceArns' --output text)
echo "Container instances: ${CONTAINER_INSTANCES}"

# Step 9: Register Task Definition for EC2
echo ""
echo "${YELLOW}Step 9: Registering task definition for EC2...${NC}"

cat > /tmp/task-definition-ec2.json <<EOF
{
  "family": "${TASK_FAMILY}",
  "networkMode": "bridge",
  "requiresCompatibilities": ["EC2"],
  "cpu": "1024",
  "memory": "3072",
  "containerDefinitions": [
    {
      "name": "fyntrix-backend",
      "image": "${ECR_URI}",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": $(cat ecs-environment.json),
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/${TASK_FAMILY}",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c \"import requests; requests.get('http://localhost:8000/health', timeout=5)\" || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
EOF

aws ecs register-task-definition \
    --cli-input-json file:///tmp/task-definition-ec2.json \
    --region ${AWS_REGION}

echo "${GREEN}✓ Task definition registered${NC}"

# Step 10: Create ECS Service
echo ""
echo "${YELLOW}Step 10: Creating ECS service...${NC}"

aws ecs create-service \
    --cluster ${CLUSTER_NAME} \
    --service-name ${SERVICE_NAME} \
    --task-definition ${TASK_FAMILY} \
    --desired-count 1 \
    --launch-type EC2 \
    --region ${AWS_REGION}

echo "${GREEN}✓ ECS service created${NC}"

# Step 11: Wait for service to stabilize
echo ""
echo "${YELLOW}Step 11: Waiting for service to stabilize...${NC}"
aws ecs wait services-stable \
    --cluster ${CLUSTER_NAME} \
    --services ${SERVICE_NAME} \
    --region ${AWS_REGION}

echo "${GREEN}✓ Service is stable${NC}"

# Step 12: Get EC2 instance public IP
echo ""
echo "${YELLOW}Step 12: Getting instance details...${NC}"

INSTANCE_ID=$(aws autoscaling describe-auto-scaling-groups \
    --auto-scaling-group-names ${ASG_NAME} \
    --region ${AWS_REGION} \
    --query 'AutoScalingGroups[0].Instances[0].InstanceId' \
    --output text)

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids ${INSTANCE_ID} \
    --region ${AWS_REGION} \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "${GREEN}=======================================${NC}"
echo "${GREEN}✓ Deployment completed successfully!${NC}"
echo "${GREEN}=======================================${NC}"
echo ""
echo "Instance Type: ${INSTANCE_TYPE}"
echo "Instance ID: ${INSTANCE_ID}"
echo "Public IP: ${PUBLIC_IP}"
echo ""
echo "Service URL: http://${PUBLIC_IP}:8000"
echo "API Docs: http://${PUBLIC_IP}:8000/docs"
echo "Health Check: http://${PUBLIC_IP}:8000/health"
echo ""
echo "SSH Access: ssh -i ~/.ssh/${KEY_NAME}.pem ec2-user@${PUBLIC_IP}"
echo ""
echo "To view logs:"
echo "  aws logs tail /ecs/${TASK_FAMILY} --follow --region ${AWS_REGION}"
echo ""
