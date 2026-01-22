# Fyntrix Backend - Terraform Infrastructure

Complete Infrastructure-as-Code (IaC) for Fyntrix backend deployment on AWS.

## 📋 Overview

This Terraform configuration manages the entire Fyntrix infrastructure:

- **Cognito User Pool** with MFA and phone number authentication
- **Lambda Functions** for custom OTP-based auth flow
- **ECS Cluster** on EC2 for container orchestration
- **RDS PostgreSQL** database
- **VPC and Networking** with public/private subnets
- **IAM Roles and Policies** for all services
- **ECR Repository** for Docker images

## 🏗️ Architecture

```
├── main.tf                 # Root module orchestration
├── variables.tf            # Input variables
├── outputs.tf              # Output values
├── modules/
│   ├── cognito/           # User authentication with MFA
│   ├── lambda/            # OTP auth Lambda functions
│   ├── iam/               # IAM roles and policies
│   ├── networking/        # VPC, subnets, NAT gateways
│   ├── rds/               # PostgreSQL database
│   └── ecs/               # ECS cluster (simplified)
└── environments/
    └── production/        # Production configuration
```

## 🚀 Quick Start

### Prerequisites

1. **Terraform** installed (>= 1.0)
   ```bash
   brew install terraform
   ```

2. **AWS CLI** configured with fyntrix profile
   ```bash
   aws configure --profile fyntrix
   ```

3. **Existing Resources** (if migrating):
   - EC2 key pair: `fyntrix-key`
   - Route53 hosted zone for `fyntrix.ai`

### Initial Setup

1. **Navigate to terraform directory**:
   ```bash
   cd terraform
   ```

2. **Create production configuration**:
   ```bash
   cp environments/production/terraform.tfvars.example terraform.tfvars
   ```

3. **Edit terraform.tfvars** with your values:
   ```bash
   nano terraform.tfvars
   ```

4. **Initialize Terraform**:
   ```bash
   terraform init
   ```

5. **Review the plan**:
   ```bash
   terraform plan
   ```

6. **Apply the configuration**:
   ```bash
   terraform apply
   ```

## 📦 What Gets Created

### Core Infrastructure

- **VPC** (`10.0.0.0/16`)
  - 2 Public subnets
  - 2 Private subnets
  - Internet Gateway
  - 2 NAT Gateways
  - Route tables

- **RDS PostgreSQL**
  - Engine: PostgreSQL 15.4
  - Instance: db.t3.micro (configurable)
  - Storage: 20GB encrypted
  - Automated backups (7 days)
  - Multi-AZ capable

- **Cognito User Pool**
  - MFA enabled (SMS + TOTP)
  - Phone number required
  - Custom auth flow with OTP
  - Google OAuth integration
  - Lambda triggers configured

- **Lambda Functions** (3)
  - Define Auth Challenge
  - Create Auth Challenge (OTP generation)
  - Verify Auth Challenge (OTP validation)

- **ECR Repository**
  - Image scanning enabled
  - Encryption enabled

- **IAM Roles**
  - ECS task execution role
  - ECS task role (with Cognito permissions)
  - ECS instance role
  - Lambda execution role
  - Cognito SNS role (for SMS)

### Security Groups

- **ECS Security Group**: Ports 80, 443, 8000, 22
- **RDS Security Group**: Port 5432 (from ECS only)

## 🔧 Configuration

### Environment Variables

Key variables in `terraform.tfvars`:

```hcl
# Database
db_username = "fintrixAdmin"
db_password = "your-secure-password"

# Google OAuth
google_client_id     = "your-google-client-id"
google_client_secret = "your-google-client-secret"

# Domain
domain_name     = "api.fyntrix.ai"
certificate_arn = "arn:aws:acm:..."
```

### Cognito Configuration

The Cognito module creates:
- User pool with phone number as username
- MFA enabled (SMS + TOTP)
- Custom auth flow for OTP
- Google identity provider
- User pool client with OAuth flows

### Lambda Functions

Three Lambda functions handle custom OTP authentication:

1. **Define Auth Challenge**: Determines auth flow
2. **Create Auth Challenge**: Generates and sends OTP via SMS
3. **Verify Auth Challenge**: Validates user-entered OTP

## 📊 Outputs

After `terraform apply`, you'll get:

```bash
# View all outputs
terraform output

# Specific outputs
terraform output cognito_user_pool_id
terraform output database_url
terraform output ecr_repository_url
```

Key outputs:
- `cognito_user_pool_id`: For backend configuration
- `cognito_user_pool_client_id`: For frontend
- `database_url`: PostgreSQL connection string
- `ecr_repository_url`: For Docker image push
- `api_url`: Application endpoint

## 🔄 Deployment Workflow

### 1. Infrastructure Setup (One-time)

```bash
cd terraform
terraform init
terraform apply
```

### 2. Build and Push Docker Image

```bash
# Get ECR repository URL
ECR_URL=$(terraform output -raw ecr_repository_url)

# Authenticate Docker to ECR
aws ecr get-login-password --region ap-south-1 --profile fyntrix | \
  docker login --username AWS --password-stdin $ECR_URL

# Build for x86_64 architecture
docker buildx build \
  --platform linux/amd64 \
  -t $ECR_URL:latest \
  --push \
  .
```

### 3. Deploy to ECS

**Note**: The ECS module is simplified. For full ECS deployment, use the existing deployment scripts:

```bash
# Use the existing deployment script
./scripts/deploy-to-ecs-ec2.sh
```

This script handles:
- EC2 instance provisioning
- ECS task definition
- Service creation
- Load balancer setup
- Auto-scaling configuration

### 4. Update Application

```bash
# Rebuild and push image
docker buildx build --platform linux/amd64 -t $ECR_URL:latest --push .

# Force ECS service update
aws ecs update-service \
  --cluster $(terraform output -raw ecs_cluster_name) \
  --service fyntrix-backend-service \
  --force-new-deployment \
  --region ap-south-1 \
  --profile fyntrix
```

## 🔐 Security Best Practices

### Secrets Management

**DO NOT** commit `terraform.tfvars` with sensitive data. Instead:

1. **Use AWS Secrets Manager** (recommended):
   ```hcl
   data "aws_secretsmanager_secret_version" "db_password" {
     secret_id = "fyntrix/db-password"
   }
   ```

2. **Use environment variables**:
   ```bash
   export TF_VAR_db_password="your-password"
   terraform apply
   ```

3. **Use encrypted `.tfvars` files** with git-crypt or similar

### State Management

For production, use remote state:

```hcl
# In main.tf
terraform {
  backend "s3" {
    bucket         = "fyntrix-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    dynamodb_table = "fyntrix-terraform-locks"
  }
}
```

Create the S3 bucket and DynamoDB table:

```bash
# Create S3 bucket
aws s3 mb s3://fyntrix-terraform-state --region ap-south-1 --profile fyntrix

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket fyntrix-terraform-state \
  --versioning-configuration Status=Enabled \
  --profile fyntrix

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name fyntrix-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-south-1 \
  --profile fyntrix
```

## 📝 Common Operations

### Update Database Password

```bash
# Update in terraform.tfvars
db_password = "new-secure-password"

# Apply changes
terraform apply -target=module.rds
```

### Scale ECS Tasks

```bash
# Update desired count
desired_count = 2

# Apply
terraform apply -target=module.ecs
```

### Add New Environment Variable

```bash
# In main.tf, add to environment_variables
environment_variables = {
  NEW_VAR = "value"
  # ... existing vars
}

# Apply
terraform apply
```

### Destroy Infrastructure

```bash
# Destroy everything (CAUTION!)
terraform destroy

# Destroy specific module
terraform destroy -target=module.ecs
```

## 🐛 Troubleshooting

### Lambda Functions Not Working

Check Lambda permissions:
```bash
aws lambda get-policy \
  --function-name $(terraform output -raw lambda_define_auth_arn) \
  --profile fyntrix
```

### Cognito SMS Not Sending

Verify SNS role:
```bash
aws iam get-role \
  --role-name $(terraform output -raw cognito_sns_role_arn | cut -d'/' -f2) \
  --profile fyntrix
```

### RDS Connection Issues

Check security group:
```bash
aws ec2 describe-security-groups \
  --group-ids $(terraform output -raw db_security_group_id) \
  --profile fyntrix
```

## 📚 Module Documentation

### Cognito Module

**Inputs**:
- `google_client_id`: Google OAuth client ID
- `google_client_secret`: Google OAuth client secret
- `define_auth_challenge_arn`: Lambda ARN
- `create_auth_challenge_arn`: Lambda ARN
- `verify_auth_challenge_arn`: Lambda ARN

**Outputs**:
- `user_pool_id`: Cognito User Pool ID
- `user_pool_client_id`: App client ID
- `user_pool_client_secret`: App client secret

### RDS Module

**Inputs**:
- `db_name`: Database name
- `db_username`: Master username
- `db_password`: Master password
- `db_instance_class`: Instance type
- `allocated_storage`: Storage in GB

**Outputs**:
- `db_endpoint`: Database endpoint
- `db_address`: Database address
- `db_port`: Database port

### Lambda Module

**Inputs**:
- `lambda_execution_role_arn`: IAM role ARN
- `user_pool_id`: Cognito User Pool ID

**Outputs**:
- `define_auth_challenge_arn`: Lambda ARN
- `create_auth_challenge_arn`: Lambda ARN
- `verify_auth_challenge_arn`: Lambda ARN

## 🔗 Integration with Existing Infrastructure

If you have existing resources:

### Import Existing Resources

```bash
# Import Cognito User Pool
terraform import module.cognito.aws_cognito_user_pool.main ap-south-1_k7eaenYhs

# Import RDS Instance
terraform import module.rds.aws_db_instance.main fyntrix-production-db

# Import ECR Repository
terraform import aws_ecr_repository.backend fyntrix-backend
```

### Use Existing VPC

```hcl
# In main.tf, replace networking module with data source
data "aws_vpc" "existing" {
  id = "vpc-xxxxx"
}

# Use in other modules
vpc_id = data.aws_vpc.existing.id
```

## 📞 Support

For issues or questions:
1. Check the [troubleshooting section](#-troubleshooting)
2. Review AWS CloudWatch logs
3. Check Terraform state: `terraform show`
4. Validate configuration: `terraform validate`

## 🎯 Next Steps

After infrastructure is deployed:

1. **Configure DNS**: Point your domain to the load balancer
2. **Setup SSL**: Create ACM certificate and update `certificate_arn`
3. **Enable monitoring**: Configure CloudWatch alarms
4. **Setup CI/CD**: Integrate with GitHub Actions or similar
5. **Backup strategy**: Configure automated RDS snapshots

## 📄 License

This infrastructure code is part of the Fyntrix project.
