# Cognito Module Variables

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "define_auth_challenge_arn" {
  description = "ARN of Define Auth Challenge Lambda"
  type        = string
}

variable "create_auth_challenge_arn" {
  description = "ARN of Create Auth Challenge Lambda"
  type        = string
}

variable "verify_auth_challenge_arn" {
  description = "ARN of Verify Auth Challenge Lambda"
  type        = string
}

variable "sns_caller_arn" {
  description = "ARN of SNS role for SMS"
  type        = string
}

variable "google_client_id" {
  description = "Google OAuth client ID"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  sensitive   = true
}

variable "callback_urls" {
  description = "List of callback URLs for OAuth"
  type        = list(string)
  default     = ["https://api.fyntrix.ai/auth/callback", "http://localhost:3000/auth/callback"]
}

variable "logout_urls" {
  description = "List of logout URLs for OAuth"
  type        = list(string)
  default     = ["https://api.fyntrix.ai/auth/logout", "http://localhost:3000/auth/logout"]
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
