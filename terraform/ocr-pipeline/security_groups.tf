# -----------------------------------------------------------
# Security Group: ocr-rds-sg (sg-01dd61603e1931ecd)
# Allows PostgreSQL inbound from within the VPC
# Used by: db-init Lambda, Aurora cluster
# -----------------------------------------------------------
resource "aws_security_group" "ocr_rds_sg" {
  name        = "ocr-rds-sg"
  description = "Created by RDS management console"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["172.31.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# -----------------------------------------------------------
# Security Group: default VPC sg (sg-006065c5ca0e2dade)
# Self-referencing — all traffic within the group allowed
# Used by: ocr-trigger, ocr-processor Lambdas
# -----------------------------------------------------------
resource "aws_security_group" "ocr_lambda_default_sg" {
  name        = "default"
  description = "default VPC security group"
  vpc_id      = var.vpc_id

  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
