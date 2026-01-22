# Fyntrix Backend - Terraform Outputs

# Networking Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.networking.vpc_id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.networking.private_subnet_ids
}

# Cognito Outputs
output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN"
  value       = module.cognito.user_pool_arn
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.cognito.user_pool_client_id
}

output "cognito_user_pool_client_secret" {
  description = "Cognito User Pool Client Secret"
  value       = module.cognito.user_pool_client_secret
  sensitive   = true
}

output "cognito_domain" {
  description = "Cognito domain for hosted UI"
  value       = module.cognito.user_pool_domain
}

# Lambda Outputs
output "lambda_define_auth_arn" {
  description = "Define Auth Challenge Lambda ARN"
  value       = module.lambda.define_auth_challenge_arn
}

output "lambda_create_auth_arn" {
  description = "Create Auth Challenge Lambda ARN"
  value       = module.lambda.create_auth_challenge_arn
}

output "lambda_verify_auth_arn" {
  description = "Verify Auth Challenge Lambda ARN"
  value       = module.lambda.verify_auth_challenge_arn
}

# RDS Outputs
output "rds_endpoint" {
  description = "RDS endpoint"
  value       = module.rds.db_endpoint
}

output "rds_database_name" {
  description = "RDS database name"
  value       = module.rds.db_name
}

output "database_url" {
  description = "Full database connection URL"
  value       = "postgresql://${var.db_username}:${var.db_password}@${module.rds.db_endpoint}/${var.db_name}?sslmode=require"
  sensitive   = true
}

# ECR Outputs
output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_arn" {
  description = "ECR repository ARN"
  value       = aws_ecr_repository.backend.arn
}

# ECS Outputs
output "ecs_cluster_id" {
  description = "ECS cluster ID"
  value       = module.ecs.cluster_id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.ecs.service_name
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = module.ecs.alb_dns_name
}

output "alb_url" {
  description = "Application Load Balancer URL"
  value       = "https://${module.ecs.alb_dns_name}"
}

output "api_url" {
  description = "API URL (custom domain or ALB)"
  value       = var.create_route53_record ? "https://${var.domain_name}" : "https://${module.ecs.alb_dns_name}"
}

# EC2 Instance Outputs
output "ec2_instance_id" {
  description = "EC2 instance ID running ECS tasks"
  value       = module.ecs.ec2_instance_id
}

output "ec2_public_ip" {
  description = "EC2 instance public IP"
  value       = module.ecs.ec2_public_ip
}

# IAM Outputs
output "ecs_task_execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = module.iam.ecs_task_execution_role_arn
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN"
  value       = module.iam.ecs_task_role_arn
}

# Summary Output
output "deployment_summary" {
  description = "Deployment summary with all important endpoints"
  value = {
    environment         = var.environment
    region             = var.aws_region
    api_url            = var.create_route53_record ? "https://${var.domain_name}" : "https://${module.ecs.alb_dns_name}"
    cognito_user_pool  = module.cognito.user_pool_id
    database_endpoint  = module.rds.db_endpoint
    ecr_repository     = aws_ecr_repository.backend.repository_url
    ecs_cluster        = module.ecs.cluster_name
  }
}
