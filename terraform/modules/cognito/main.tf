# Cognito User Pool with MFA and Lambda Triggers

resource "aws_cognito_user_pool" "main" {
  name = "${var.name_prefix}-user-pool"

  # Username configuration
  username_attributes      = ["email", "phone_number"]
  auto_verified_attributes = ["email", "phone_number"]

  username_configuration {
    case_sensitive = false
  }

  # Password policy
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  # MFA Configuration
  mfa_configuration = "ON"
  
  software_token_mfa_configuration {
    enabled = true
  }

  sms_configuration {
    external_id    = "${var.name_prefix}-external"
    sns_caller_arn = var.sns_caller_arn
    sns_region     = data.aws_region.current.name
  }

  # User attributes schema
  schema {
    name                = "email"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    
    string_attribute_constraints {
      min_length = 0
      max_length = 2048
    }
  }

  schema {
    name                = "phone_number"
    attribute_data_type = "String"
    mutable             = true
    required            = true
    
    string_attribute_constraints {
      min_length = 0
      max_length = 2048
    }
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    mutable             = true
    required            = true
    
    string_attribute_constraints {
      min_length = 0
      max_length = 2048
    }
  }

  schema {
    name                = "pan_number"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    developer_only_attribute = false
    
    string_attribute_constraints {
      min_length = 10
      max_length = 10
    }
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
    recovery_mechanism {
      name     = "verified_phone_number"
      priority = 2
    }
  }

  # Admin create user config
  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  # Email configuration
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  # Verification message template
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }

  # Lambda triggers for custom auth flow
  lambda_config {
    define_auth_challenge          = var.define_auth_challenge_arn
    create_auth_challenge          = var.create_auth_challenge_arn
    verify_auth_challenge_response = var.verify_auth_challenge_arn
  }

  tags = var.tags
}

# Cognito User Pool Domain
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.name_prefix}-${random_string.domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "random_string" "domain_suffix" {
  length  = 8
  special = false
  upper   = false
}

# Cognito User Pool Client
resource "aws_cognito_user_pool_client" "main" {
  name         = "${var.name_prefix}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = true

  # OAuth configuration
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code", "implicit"]
  allowed_oauth_scopes                 = ["email", "openid", "phone", "profile"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  supported_identity_providers         = ["COGNITO", "Google"]

  # Token validity
  access_token_validity  = 60  # minutes
  id_token_validity      = 60  # minutes
  refresh_token_validity = 30  # days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  # Auth flows
  explicit_auth_flows = [
    "ALLOW_CUSTOM_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH"
  ]

  # Prevent user existence errors
  prevent_user_existence_errors = "ENABLED"

  # Read and write attributes
  read_attributes = [
    "email",
    "email_verified",
    "phone_number",
    "phone_number_verified",
    "name",
    "custom:pan_number"
  ]

  write_attributes = [
    "email",
    "phone_number",
    "name",
    "custom:pan_number"
  ]
}

# Google Identity Provider
resource "aws_cognito_identity_provider" "google" {
  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    authorize_scopes = "email openid profile"
    client_id        = var.google_client_id
    client_secret    = var.google_client_secret
  }

  attribute_mapping = {
    email    = "email"
    username = "sub"
    name     = "name"
  }
}

# Data sources
data "aws_region" "current" {}
