# Lambda Functions for Cognito Custom Auth Flow

# Define Auth Challenge Lambda
resource "aws_lambda_function" "define_auth_challenge" {
  filename         = data.archive_file.define_auth.output_path
  function_name    = "${var.name_prefix}-define-auth-challenge"
  role            = var.lambda_execution_role_arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.define_auth.output_base64sha256
  runtime         = "python3.12"
  timeout         = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }

  tags = var.tags
}

# Create Auth Challenge Lambda
resource "aws_lambda_function" "create_auth_challenge" {
  filename         = data.archive_file.create_auth.output_path
  function_name    = "${var.name_prefix}-create-auth-challenge"
  role            = var.lambda_execution_role_arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.create_auth.output_base64sha256
  runtime         = "python3.12"
  timeout         = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }

  tags = var.tags
}

# Verify Auth Challenge Lambda
resource "aws_lambda_function" "verify_auth_challenge" {
  filename         = data.archive_file.verify_auth.output_path
  function_name    = "${var.name_prefix}-verify-auth-challenge"
  role            = var.lambda_execution_role_arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = data.archive_file.verify_auth.output_base64sha256
  runtime         = "python3.12"
  timeout         = 30

  environment {
    variables = {
      ENVIRONMENT = var.environment
    }
  }

  tags = var.tags
}

# Lambda permissions for Cognito
resource "aws_lambda_permission" "cognito_define_auth" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.define_auth_challenge.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = "arn:aws:cognito-idp:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:userpool/${var.user_pool_id}"
}

resource "aws_lambda_permission" "cognito_create_auth" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.create_auth_challenge.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = "arn:aws:cognito-idp:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:userpool/${var.user_pool_id}"
}

resource "aws_lambda_permission" "cognito_verify_auth" {
  statement_id  = "AllowCognitoInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.verify_auth_challenge.function_name
  principal     = "cognito-idp.amazonaws.com"
  source_arn    = "arn:aws:cognito-idp:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:userpool/${var.user_pool_id}"
}

# Archive Lambda function code
data "archive_file" "define_auth" {
  type        = "zip"
  source_dir  = "${path.module}/functions/define_auth_challenge"
  output_path = "${path.module}/functions/define_auth_challenge.zip"
}

data "archive_file" "create_auth" {
  type        = "zip"
  source_dir  = "${path.module}/functions/create_auth_challenge"
  output_path = "${path.module}/functions/create_auth_challenge.zip"
}

data "archive_file" "verify_auth" {
  type        = "zip"
  source_dir  = "${path.module}/functions/verify_auth_challenge"
  output_path = "${path.module}/functions/verify_auth_challenge.zip"
}

# Data sources
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
