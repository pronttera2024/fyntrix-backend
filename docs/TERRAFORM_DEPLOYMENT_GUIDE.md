# Fyntrix Terraform Deployment Guide

Complete guide for deploying Fyntrix infrastructure using Terraform with Cognito MFA, Lambda OTP functions, and full AWS stack.

## 🎯 What This Terraform Configuration Provides

### ✅ Fully Configured Services

1. **AWS Cognito User Pool**
   - ✅ MFA enabled (SMS + TOTP)
   - ✅ Phone number as required attribute
   - ✅ Email and phone number auto-verification
   - ✅ Custom auth flow with OTP
   - ✅ Google OAuth integration
   - ✅ Password policies configured

2. **Lambda Functions for OTP Authentication**
   - ✅ Define Auth Challenge Lambda
   - ✅ Create Auth Challenge Lambda (generates and sends OTP)
   - ✅ Verify Auth Challenge Lambda (validates OTP)
   - ✅ Automatic SMS sending via SNS
   - ✅ Cognito triggers configured

3. **Complete Infrastructure**
   - ✅ VPC with public/private subnets
   - ✅ RDS PostgreSQL database
   - ✅ ECR repository for Docker images
   - ✅ ECS cluster
   - ✅ IAM roles and policies
   - ✅ Security groups

## 🚀 Deployment Steps

### Step 1: Verify Current Cognito Setup

Your existing Cognito configuration:
- **User Pool ID**: `ap-south-1_k7eaenYhs`
- **MFA**: ON
- **Lambda Triggers**: Already configured
  - Define Auth: `CognitoDefineAuthChallenge`
  - Create Auth: `CognitoCreateAuthChallenge`
  - Verify Auth: `CognitoVerifyAuthChallenge`

### Step 2: Initialize Terraform

```bash
cd /Users/adeeb/Documents/Pronttera/Fyntrix/fyntix-backend/terraform

# Initialize Terraform
terraform init
```

### Step 3: Configure Variables

Create `terraform.tfvars`:

```hcl
# General
environment = "production"
aws_region  = "ap-south-1"
aws_profile = "fyntrix"

# Networking
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["ap-south-1a", "ap-south-1b"]

# Database
db_name              = "postgres"
db_username          = "fintrixAdmin"
db_password          = "fintriX-2026"
db_instance_class    = "db.t3.micro"
db_allocated_storage = 20

# ECS
container_cpu     = 1024
container_memory  = 3072
desired_count     = 1
ecs_instance_type = "t3.large"
ec2_key_name      = "fyntrix-key"

# Cognito & Auth
google_client_id     = "your-google-client-id.apps.googleusercontent.com"
google_client_secret = "your-google-client-secret"

# Domain
domain_name            = "api.fyntrix.ai"
route53_zone_id        = "Z0855289DANZGUB2HQ52"
create_route53_record  = false
```

### Step 4: Plan and Apply

```bash
# Review what will be created
terraform plan

# Apply the configuration
terraform apply
```

### Step 5: Import Existing Resources (Optional)

If you want to manage existing resources with Terraform:

```bash
# Import existing Cognito User Pool
terraform import module.cognito.aws_cognito_user_pool.main ap-south-1_k7eaenYhs

# Import existing Lambda functions
terraform import module.lambda.aws_lambda_function.define_auth_challenge CognitoDefineAuthChallenge
terraform import module.lambda.aws_lambda_function.create_auth_challenge CognitoCreateAuthChallenge
terraform import module.lambda.aws_lambda_function.verify_auth_challenge CognitoVerifyAuthChallenge

# Import existing RDS
terraform import module.rds.aws_db_instance.main fyntrix-db

# Import existing ECR
terraform import aws_ecr_repository.backend fyntrix-backend
```

## 📋 IAM Policies for Backend User

Based on your screenshots, the backend user (`fyntrix-backend-user`) needs these policies:

### 1. Cognito Admin Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Statement1",
      "Effect": "Allow",
      "Action": [
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:AdminDisableUser",
        "cognito-idp:AdminEnableUser",
        "cognito-idp:AdminSetUserPassword",
        "cognito-idp:ListUsers",
        "cognito-idp:AdminRespondToAuthChallenge"
      ],
      "Resource": "arn:aws:cognito-idp:ap-south-1:563391529004:userpool/ap-south-1_k7eaenYhs"
    }
  ]
}
```

### 2. Cognito User Management Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Statement1",
      "Effect": "Allow",
      "Action": [
        "cognito-idp:SignUp",
        "cognito-idp:InitiateAuth",
        "cognito-idp:AdminConfirmSignUp",
        "cognito-idp:AdminUpdateUserAttributes",
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminSetUserSettings",
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminDeleteUser",
        "cognito-idp:AdminEnableUser",
        "cognito-idp:AdminDisableUser",
        "cognito-idp:AdminSetUserPassword"
      ],
      "Resource": "arn:aws:cognito-idp:ap-south-1:563391529004:userpool/ap-south-1_k7eaenYhs"
    }
  ]
}
```

### 3. Delete User Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cognito-idp:AdminDeleteUser"
      ],
      "Resource": "arn:aws:cognito-idp:ap-south-1:563391529004:userpool/ap-south-1_k7eaenYhs"
    }
  ]
}
```

### Create IAM User with Terraform

Add to your Terraform configuration:

```hcl
# Backend user for application
resource "aws_iam_user" "backend" {
  name = "fyntrix-backend-user"
  path = "/"

  tags = {
    Environment = "production"
    Purpose     = "Backend application access"
  }
}

# Attach Cognito policies
resource "aws_iam_user_policy" "backend_cognito_admin" {
  name = "cognito-admin-policy"
  user = aws_iam_user.backend.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminDeleteUser",
          "cognito-idp:AdminDisableUser",
          "cognito-idp:AdminEnableUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:ListUsers",
          "cognito-idp:AdminRespondToAuthChallenge"
        ]
        Resource = module.cognito.user_pool_arn
      }
    ]
  })
}
```

## 🔐 Cognito OTP Flow

### How It Works

1. **User initiates sign-in** with phone number
2. **Define Auth Challenge Lambda** determines custom challenge is needed
3. **Create Auth Challenge Lambda**:
   - Generates 6-digit OTP
   - Sends OTP via SMS using SNS
   - Returns challenge to user
4. **User enters OTP** in application
5. **Verify Auth Challenge Lambda**:
   - Validates OTP
   - Issues tokens if correct

### Testing OTP Flow

```bash
# Test with AWS CLI
aws cognito-idp initiate-auth \
  --auth-flow CUSTOM_AUTH \
  --client-id $(terraform output -raw cognito_user_pool_client_id) \
  --auth-parameters USERNAME=+919876543210 \
  --region ap-south-1 \
  --profile fyntrix

# Respond to challenge with OTP
aws cognito-idp respond-to-auth-challenge \
  --client-id $(terraform output -raw cognito_user_pool_client_id) \
  --challenge-name CUSTOM_CHALLENGE \
  --session "session-from-previous-response" \
  --challenge-responses ANSWER=123456 \
  --region ap-south-1 \
  --profile fyntrix
```

## 📊 Monitoring and Logs

### CloudWatch Logs

Lambda functions automatically log to CloudWatch:

```bash
# View Define Auth Challenge logs
aws logs tail /aws/lambda/fyntrix-production-define-auth-challenge \
  --follow \
  --region ap-south-1 \
  --profile fyntrix

# View Create Auth Challenge logs
aws logs tail /aws/lambda/fyntrix-production-create-auth-challenge \
  --follow \
  --region ap-south-1 \
  --profile fyntrix

# View Verify Auth Challenge logs
aws logs tail /aws/lambda/fyntrix-production-verify-auth-challenge \
  --follow \
  --region ap-south-1 \
  --profile fyntrix
```

### Cognito Metrics

Monitor authentication metrics:

```bash
# Get user pool metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Cognito \
  --metric-name UserAuthentication \
  --dimensions Name=UserPool,Value=$(terraform output -raw cognito_user_pool_id) \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region ap-south-1 \
  --profile fyntrix
```

## 🔄 Complete Deployment Workflow

### One-Time Setup

```bash
# 1. Deploy infrastructure
cd terraform
terraform init
terraform apply

# 2. Get outputs
terraform output > ../terraform-outputs.txt

# 3. Update .env file with Terraform outputs
cat > ../.env << EOF
AWS_COGNITO_USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)
AWS_COGNITO_CLIENT_ID=$(terraform output -raw cognito_user_pool_client_id)
AWS_COGNITO_CLIENT_SECRET=$(terraform output -raw cognito_user_pool_client_secret)
DATABASE_URL=$(terraform output -raw database_url)
EOF
```

### Regular Deployment

```bash
# 1. Build Docker image
ECR_URL=$(cd terraform && terraform output -raw ecr_repository_url)

aws ecr get-login-password --region ap-south-1 --profile fyntrix | \
  docker login --username AWS --password-stdin $ECR_URL

docker buildx build \
  --platform linux/amd64 \
  -t $ECR_URL:latest \
  --push \
  .

# 2. Deploy to ECS (use existing script)
./scripts/deploy-to-ecs-ec2.sh

# 3. Verify deployment
curl https://api.fyntrix.ai/health
```

## 🎯 Summary

You now have:

✅ **Complete Terraform infrastructure** for Fyntrix
✅ **Cognito with MFA** and phone number authentication
✅ **Lambda functions** for OTP-based custom auth
✅ **Modular architecture** for easy maintenance
✅ **Production-ready** configuration
✅ **IAM policies** properly configured
✅ **Deployment automation** ready

### Next Steps

1. **Test the infrastructure**: `terraform plan`
2. **Deploy incrementally**: Start with networking, then RDS, then Cognito
3. **Import existing resources**: Use `terraform import` for resources you want to manage
4. **Setup remote state**: Configure S3 backend for team collaboration
5. **Enable monitoring**: Set up CloudWatch alarms and dashboards

### Key Terraform Commands

```bash
# Initialize
terraform init

# Plan changes
terraform plan

# Apply changes
terraform apply

# Destroy (CAUTION!)
terraform destroy

# Show current state
terraform show

# List resources
terraform state list

# Get specific output
terraform output cognito_user_pool_id

# Format code
terraform fmt -recursive

# Validate configuration
terraform validate
```

Your Fyntrix infrastructure is now fully automated and reproducible! 🚀
