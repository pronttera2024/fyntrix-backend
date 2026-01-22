# Fyntrix Backend - Main Terraform Configuration
# This is the root module that orchestrates all infrastructure components

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Backend configuration for state management
  # Uncomment and configure for production use
  # backend "s3" {
  #   bucket         = "fyntrix-terraform-state"
  #   key            = "production/terraform.tfstate"
  #   region         = "ap-south-1"
  #   encrypt        = true
  #   dynamodb_table = "fyntrix-terraform-locks"
  # }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  
  default_tags {
    tags = {
      Project     = "Fyntrix"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = "Pronttera"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Local variables
locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  
  common_tags = {
    Project     = "Fyntrix"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
  
  name_prefix = "fyntrix-${var.environment}"
}

# VPC and Networking
module "networking" {
  source = "./modules/networking"
  
  environment         = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  name_prefix        = local.name_prefix
  
  tags = local.common_tags
}

# IAM Roles and Policies
module "iam" {
  source = "./modules/iam"
  
  environment = var.environment
  name_prefix = local.name_prefix
  account_id  = local.account_id
  
  tags = local.common_tags
}

# Cognito User Pool with MFA and Lambda Triggers
module "cognito" {
  source = "./modules/cognito"
  
  environment = var.environment
  name_prefix = local.name_prefix
  
  # Lambda function ARNs for auth triggers
  define_auth_challenge_arn       = module.lambda.define_auth_challenge_arn
  create_auth_challenge_arn       = module.lambda.create_auth_challenge_arn
  verify_auth_challenge_arn       = module.lambda.verify_auth_challenge_arn
  
  # SNS role for SMS
  sns_caller_arn = module.iam.cognito_sns_role_arn
  
  # Google OAuth configuration
  google_client_id     = var.google_client_id
  google_client_secret = var.google_client_secret
  
  tags = local.common_tags
}

# Lambda Functions for Cognito Auth
module "lambda" {
  source = "./modules/lambda"
  
  environment = var.environment
  name_prefix = local.name_prefix
  
  # IAM role for Lambda execution
  lambda_execution_role_arn = module.iam.lambda_execution_role_arn
  
  # Cognito User Pool ID (for permissions)
  user_pool_id = module.cognito.user_pool_id
  
  tags = local.common_tags
}

# RDS PostgreSQL Database
module "rds" {
  source = "./modules/rds"
  
  environment = var.environment
  name_prefix = local.name_prefix
  
  # Networking
  vpc_id              = module.networking.vpc_id
  private_subnet_ids  = module.networking.private_subnet_ids
  
  # Database configuration
  db_name             = var.db_name
  db_username         = var.db_username
  db_password         = var.db_password
  db_instance_class   = var.db_instance_class
  allocated_storage   = var.db_allocated_storage
  
  # Security
  allowed_security_group_ids = [module.ecs.ecs_security_group_id]
  
  tags = local.common_tags
}

# ECR Repository
resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = "MUTABLE"
  
  image_scanning_configuration {
    scan_on_push = true
  }
  
  encryption_configuration {
    encryption_type = "AES256"
  }
  
  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-backend"
    }
  )
}

# ECS Cluster and Services
module "ecs" {
  source = "./modules/ecs"
  
  environment = var.environment
  name_prefix = local.name_prefix
  
  # Networking
  vpc_id             = module.networking.vpc_id
  public_subnet_ids  = module.networking.public_subnet_ids
  private_subnet_ids = module.networking.private_subnet_ids
  
  # ECR
  ecr_repository_url = aws_ecr_repository.backend.repository_url
  
  # IAM
  ecs_task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  ecs_task_role_arn          = module.iam.ecs_task_role_arn
  ecs_instance_role_name     = module.iam.ecs_instance_role_name
  
  # Application configuration
  container_cpu    = var.container_cpu
  container_memory = var.container_memory
  desired_count    = var.desired_count
  
  # Environment variables
  environment_variables = {
    PORT                        = "8000"
    DATABASE_URL                = "postgresql://${var.db_username}:${var.db_password}@${module.rds.db_endpoint}/${var.db_name}?sslmode=require"
    REDIS_HOST                  = "127.0.0.1"
    REDIS_PORT                  = "6379"
    REDIS_DB                    = "0"
    AWS_COGNITO_REGION          = local.region
    AWS_COGNITO_USER_POOL_ID    = module.cognito.user_pool_id
    AWS_COGNITO_CLIENT_ID       = module.cognito.user_pool_client_id
    AWS_COGNITO_CLIENT_SECRET   = module.cognito.user_pool_client_secret
    GOOGLE_CLIENT_ID            = var.google_client_id
    GOOGLE_CLIENT_SECRET        = var.google_client_secret
    ENV_NAME                    = var.environment
    PYTHONPATH                  = "/app"
  }
  
  # EC2 instance configuration
  instance_type = var.ecs_instance_type
  key_name      = var.ec2_key_name
  
  # SSL Certificate ARN for HTTPS
  certificate_arn = var.certificate_arn
  domain_name     = var.domain_name
  
  tags = local.common_tags
}

# Route53 DNS Configuration
resource "aws_route53_record" "api" {
  count = var.create_route53_record ? 1 : 0
  
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  
  alias {
    name                   = module.ecs.alb_dns_name
    zone_id                = module.ecs.alb_zone_id
    evaluate_target_health = true
  }
}
