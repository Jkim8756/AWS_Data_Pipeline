variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-2"
}

variable "upload_bucket_name" {
  description = "S3 bucket where staff upload timesheet PDFs"
  type        = string
  default     = "timesheets-pdf-uploads-01"
}

variable "raw_json_bucket_name" {
  description = "S3 bucket for raw Claude JSON output (audit/replay)"
  type        = string
  default     = "timesheet-scanned-raw-json01"
}

variable "sqs_queue_name" {
  description = "SQS queue name for OCR processing"
  type        = string
  default     = "timesheet-process-queue"
}

variable "sqs_dlq_name" {
  description = "Dead-letter queue name for failed OCR messages"
  type        = string
  default     = "timesheet-dlq"
}

variable "ecr_repo_name" {
  description = "ECR repository name for the Lambda container image"
  type        = string
  default     = "timesheets-ocr-lambda"
}

variable "lambda_function_name" {
  description = "Lambda function name"
  type        = string
  default     = "timesheet-etl"
}

variable "anthropic_api_key" {
  description = "Anthropic API key for Claude Vision"
  type        = string
  sensitive   = true
}

variable "db_host" {
  description = "Supabase PostgreSQL host"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "postgres"
}

variable "db_user" {
  description = "Database user"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "db_port" {
  description = "Database port (5432 for Session Pooler)"
  type        = string
  default     = "5432"
}
