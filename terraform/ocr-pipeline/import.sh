#!/bin/bash
# import.sh — Run once to pull existing AWS resources into Terraform state
# Prerequisites: terraform init must be run first
# Usage: bash import.sh

set -e

ACCOUNT="569239323358"
REGION="us-east-1"

echo "=== Importing IAM Roles ==="
terraform import aws_iam_role.ocr_pipeline_lambda_role          ocr-pipeline-lambda-role
terraform import aws_iam_role.textract_sns_role                 textract-sns-role
terraform import aws_iam_role.rds_monitoring_role               rds-monitoring-role

echo "=== Importing IAM Policy ==="
terraform import aws_iam_policy.ocr_pipeline_lambda_policy      arn:aws:iam::${ACCOUNT}:policy/ocr-pipeline-lambda-policy

echo "=== Importing IAM Attachments ==="
terraform import aws_iam_role_policy_attachment.lambda_custom_policy   ocr-pipeline-lambda-role/arn:aws:iam::${ACCOUNT}:policy/ocr-pipeline-lambda-policy
terraform import aws_iam_role_policy_attachment.lambda_vpc_execution   ocr-pipeline-lambda-role/arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole
terraform import aws_iam_role_policy_attachment.textract_service_role  textract-sns-role/arn:aws:iam::aws:policy/service-role/AmazonTextractServiceRole
terraform import aws_iam_role_policy_attachment.rds_enhanced_monitoring rds-monitoring-role/arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole

echo "=== Importing Security Groups ==="
terraform import aws_security_group.ocr_rds_sg              sg-01dd61603e1931ecd
terraform import aws_security_group.ocr_lambda_default_sg   sg-006065c5ca0e2dade

echo "=== Importing S3 Buckets ==="
terraform import aws_s3_bucket.ocr_input                    ocr-input-${ACCOUNT}-${REGION}
terraform import aws_s3_bucket.timesheets_pdf_uploads        timesheets-pdf-uploads-01

echo "=== Importing SNS ==="
terraform import aws_sns_topic.textract_completion          arn:aws:sns:${REGION}:${ACCOUNT}:textract-completion
terraform import aws_sns_topic_subscription.textract_to_ocr_processor \
  arn:aws:sns:${REGION}:${ACCOUNT}:textract-completion:c0d0f11e-8716-41af-9a3c-4b1052345f75

echo "=== Importing RDS ==="
terraform import aws_db_subnet_group.ocr_db_subnet_group    default-vpc-vpc-09cfbfef6e055339a
terraform import aws_rds_cluster.ocrdb                      ocrdb
terraform import aws_rds_cluster_instance.ocrdb_instance_1  ocrdb-instance-1

echo "=== Importing Lambda Functions ==="
terraform import aws_lambda_function.ocr_trigger            ocr-trigger
terraform import aws_lambda_function.ocr_processor          ocr-processor
terraform import aws_lambda_function.db_init                db-init

echo "=== Importing Lambda Permissions ==="
terraform import aws_lambda_permission.allow_s3_invoke_trigger    ocr-trigger/lambda-277ac3e1-54fc-4f03-b9af-c9fdcf4f0d1c
terraform import aws_lambda_permission.allow_sns_invoke_processor ocr-processor/lambda-4200e3db-eb24-4ee1-81f2-1233c327a9bf

echo "=== Importing S3 Notification ==="
terraform import aws_s3_bucket_notification.ocr_input_trigger ocr-input-${ACCOUNT}-${REGION}

echo ""
echo "Import complete. Run: terraform plan"
echo "Goal: 0 changes to add/change/destroy"
