variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
  default     = "569239323358"
}

variable "db_name" {
  description = "Aurora PostgreSQL database name"
  type        = string
  default     = "ocrdb"
}

variable "db_master_username" {
  description = "Aurora PostgreSQL master username"
  type        = string
  default     = "ocruser"
}

variable "vpc_id" {
  description = "VPC ID for the pipeline resources"
  type        = string
  default     = "vpc-09cfbfef6e055339a"
}

variable "subnet_ids" {
  description = "Subnet IDs for Lambda VPC config and RDS subnet group"
  type        = list(string)
  default     = ["subnet-0a82550140602efce", "subnet-06608987a37513386"]
}
