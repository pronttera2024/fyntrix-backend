# Lambda Module Outputs

output "define_auth_challenge_arn" {
  description = "ARN of Define Auth Challenge Lambda"
  value       = aws_lambda_function.define_auth_challenge.arn
}

output "create_auth_challenge_arn" {
  description = "ARN of Create Auth Challenge Lambda"
  value       = aws_lambda_function.create_auth_challenge.arn
}

output "verify_auth_challenge_arn" {
  description = "ARN of Verify Auth Challenge Lambda"
  value       = aws_lambda_function.verify_auth_challenge.arn
}

output "define_auth_challenge_name" {
  description = "Name of Define Auth Challenge Lambda"
  value       = aws_lambda_function.define_auth_challenge.function_name
}

output "create_auth_challenge_name" {
  description = "Name of Create Auth Challenge Lambda"
  value       = aws_lambda_function.create_auth_challenge.function_name
}

output "verify_auth_challenge_name" {
  description = "Name of Verify Auth Challenge Lambda"
  value       = aws_lambda_function.verify_auth_challenge.function_name
}
