# OCR Pipeline — IaC Documentation

## Architecture

PDF uploaded to S3 → ocr-trigger Lambda → Textract (async)
→ SNS textract-completion → ocr-processor Lambda → Aurora PostgreSQL (ocrdb)

db-init Lambda is invoked manually for schema setup/migrations.

## Resources

| Resource | Type | Name/ID |
|---|---|---|
| S3 input bucket | aws_s3_bucket | ocr-input-569239323358-us-east-1 |
| S3 timesheets bucket | aws_s3_bucket | timesheets-pdf-uploads-01 |
| Lambda trigger | aws_lambda_function | ocr-trigger |
| Lambda processor | aws_lambda_function | ocr-processor |
| Lambda db init | aws_lambda_function | db-init |
| Lambda layer | aws_lambda_layer_version | psycopg2-python313 v1 |
| SNS topic | aws_sns_topic | textract-completion |
| Aurora cluster | aws_rds_cluster | ocrdb (aurora-postgresql 17.9, serverless v2) |
| Aurora instance | aws_rds_cluster_instance | ocrdb-instance-1 (db.serverless) |
| IAM role (Lambda) | aws_iam_role | ocr-pipeline-lambda-role |
| IAM role (Textract) | aws_iam_role | textract-sns-role |
| IAM role (RDS monitoring) | aws_iam_role | rds-monitoring-role |
| IAM policy | aws_iam_policy | ocr-pipeline-lambda-policy |
| Security group (RDS) | aws_security_group | ocr-rds-sg |
| Security group (Lambda) | aws_security_group | default VPC sg |
| VPC | (data source only) | vpc-09cfbfef6e055339a |

## File Structure

```
terraform/ocr-pipeline/
├── main.tf             # Provider, backend config
├── variables.tf        # Region, account ID, VPC, subnets
├── iam.tf              # All IAM roles and policies
├── security_groups.tf  # SGs for Lambda and RDS
├── s3.tf               # Input bucket + notification config
├── sns.tf              # textract-completion topic + subscription
├── rds.tf              # Aurora PostgreSQL cluster + instance
├── lambda.tf           # All three Lambda functions + permissions
├── outputs.tf          # Key ARNs and endpoints
├── import.sh           # One-time import of existing resources
└── README.md           # This file
```

## Setup Steps

### 1. Prerequisites
- Terraform >= 1.5 installed
- AWS CLI configured (`aws configure`)
- Lambda deployment zips available (see below)

### 2. Prepare Lambda zips
Before running terraform, place deployment zips alongside the .tf files:
- `ocr-trigger.zip`
- `ocr-processor.zip`
- `db-init.zip`

Download from live functions:
```bash
aws lambda get-function --function-name ocr-trigger \
  --query 'Code.Location' --output text | xargs curl -o ocr-trigger.zip
aws lambda get-function --function-name ocr-processor \
  --query 'Code.Location' --output text | xargs curl -o ocr-processor.zip
aws lambda get-function --function-name db-init \
  --query 'Code.Location' --output text | xargs curl -o db-init.zip
```

### 3. Initialize and import
```bash
cd terraform/ocr-pipeline
terraform init
bash import.sh
terraform plan   # Should show 0 changes
```

## Security Notes

1. **db-init DB_PASSWORD** — a plaintext password was detected in the live
   Lambda environment variables. This should be rotated and replaced with
   a Secrets Manager lookup using `DB_SECRET_ARN` (already used by the other
   two functions).

2. **RDS storage_encrypted = false** — the live cluster has encryption disabled.
   Consider enabling for production; requires cluster replacement.

3. **deletion_protection = false** — set to `true` for production to prevent
   accidental cluster deletion.

## Key Environment Variables (shared across Lambdas)

| Variable | Value |
|---|---|
| DB_HOST | ocrdb.cluster-cg50w40uytey.us-east-1.rds.amazonaws.com |
| DB_NAME | ocrdb |
| DB_PORT | 5432 |
| DB_SECRET_ARN | arn:aws:secretsmanager:us-east-1:569239323358:secret:ocr-pipeline/db-credentials-7dbJsg |
| TEXTRACT_ROLE_ARN | arn:aws:iam::569239323358:role/textract-sns-role |
| TEXTRACT_SNS_TOPIC_ARN | arn:aws:sns:us-east-1:569239323358:textract-completion |
