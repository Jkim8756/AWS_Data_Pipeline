# -----------------------------------------------------------
# RDS Aurora PostgreSQL Serverless v2: ocrdb
# Engine: aurora-postgresql 17.9
# Capacity: 0.5–4.0 ACUs
# -----------------------------------------------------------
resource "aws_db_subnet_group" "ocr_db_subnet_group" {
  name        = "default-vpc-09cfbfef6e055339a"
  description = "Created from the RDS Management Console"  # match live value
  subnet_ids  = [
    "subnet-0a82550140602efce",
    "subnet-06cd29d417ffd24d3",
    "subnet-06608987a37513386",
    "subnet-08270f42e85438b6b",
    "subnet-00bf7c4d723e4ca26",
    "subnet-0a1ca33cfdcdb8a86",
  ]
}

resource "aws_rds_cluster" "ocrdb" {
  cluster_identifier        = "ocrdb"
  engine                    = "aurora-postgresql"
  engine_version            = "17.9"
  engine_mode               = "provisioned"
  master_username           = var.db_master_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.ocr_db_subnet_group.name
  vpc_security_group_ids = [aws_security_group.ocr_rds_sg.id]

  backup_retention_period      = 7
  preferred_backup_window      = "08:07-08:37"
  preferred_maintenance_window = "sun:03:29-sun:03:59"

  storage_encrypted     = false
  deletion_protection   = false
  copy_tags_to_snapshot = true
  skip_final_snapshot   = true

  serverlessv2_scaling_configuration {
    min_capacity = 0.5
    max_capacity = 4.0
  }

  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  lifecycle {
    ignore_changes = [
      database_name,        # already set on existing cluster
      availability_zones,   # AWS manages AZ placement
      master_password_wo,
    ]
    prevent_destroy = true  # safety net — must set to false to ever delete
  }
}

resource "aws_rds_cluster_instance" "ocrdb_instance_1" {
  identifier          = "ocrdb-instance-1"
  cluster_identifier  = aws_rds_cluster.ocrdb.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.ocrdb.engine
  engine_version      = aws_rds_cluster.ocrdb.engine_version
  promotion_tier      = 0
  lifecycle {
    prevent_destroy = true
  }

  auto_minor_version_upgrade = true
  monitoring_interval        = 60
  monitoring_role_arn        = aws_iam_role.rds_monitoring_role.arn

  performance_insights_enabled          = true
  performance_insights_retention_period = 7
}
