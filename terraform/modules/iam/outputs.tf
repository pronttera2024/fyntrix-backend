# IAM Module Outputs

output "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_instance_role_name" {
  description = "Name of ECS instance role"
  value       = aws_iam_role.ecs_instance.name
}

output "ecs_instance_profile_name" {
  description = "Name of ECS instance profile"
  value       = aws_iam_instance_profile.ecs_instance.name
}

output "lambda_execution_role_arn" {
  description = "ARN of Lambda execution role"
  value       = aws_iam_role.lambda_execution.arn
}

output "cognito_sns_role_arn" {
  description = "ARN of Cognito SNS role"
  value       = aws_iam_role.cognito_sns.arn
}
