# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Serverless OCR pipeline on AWS:

```
PDF → S3 (ocr-input-*) → ocr-trigger Lambda → AWS Textract (async)
                                                      ↓
                                        SNS (textract-completion)
                                                      ↓
                                        ocr-processor Lambda → Aurora PostgreSQL (ocrdb)
```

- **ocr-trigger**: Fires on S3 `ObjectCreated:*.pdf`, starts an async Textract job with the SNS completion topic.
- **ocr-processor**: Subscribes to SNS, retrieves Textract results, writes extracted text to Aurora.
- **db-init**: Manually invoked Lambda for schema setup and migrations.
- All Lambdas run Python 3.13 in the default VPC, sharing the `psycopg2-python313` Lambda layer and `ocr-pipeline-lambda-role`.
- DB credentials are fetched at runtime from Secrets Manager via `DB_SECRET_ARN` (except `db-init`, which still uses a plaintext `DB_PASSWORD` — see security note below).

## Infrastructure (Terraform)

All IaC lives in `terraform/ocr-pipeline/`. State is stored locally (`terraform.tfstate`) — remote backend is stubbed out but not yet configured.

```bash
cd terraform/ocr-pipeline

# First-time import of live resources
bash import.sh

terraform init
terraform plan    # should show 0 changes against live infra
terraform apply
```

**Before applying**, Lambda deployment zips must be present alongside the `.tf` files:
```bash
# Download current live code from AWS
aws lambda get-function --function-name ocr-trigger \
  --query 'Code.Location' --output text | xargs curl -o ocr-trigger.zip
aws lambda get-function --function-name ocr-processor \
  --query 'Code.Location' --output text | xargs curl -o ocr-processor.zip
aws lambda get-function --function-name db-init \
  --query 'Code.Location' --output text | xargs curl -o db-init.zip
```

## Deploying Lambda code changes

Zip the updated handler and update the function directly, then record the change in Terraform:
```bash
zip ocr-trigger.zip lambda_function.py
aws lambda update-function-code --function-name ocr-trigger --zip-file fileb://ocr-trigger.zip
# Then move the zip to terraform/ocr-pipeline/ and run terraform plan to confirm no drift
```

## Manual pipeline test

Upload a PDF to the input bucket to trigger the full pipeline:
```bash
aws s3 cp src/input/sample.pdf s3://ocr-input-569239323358-us-east-1/
# Monitor logs
aws logs tail /aws/lambda/ocr-trigger --follow
aws logs tail /aws/lambda/ocr-processor --follow
```

## Key resources

| Resource | Name |
|---|---|
| S3 input bucket | `ocr-input-569239323358-us-east-1` |
| Aurora cluster endpoint | `ocrdb.cluster-cg50w40uytey.us-east-1.rds.amazonaws.com` |
| SNS topic | `arn:aws:sns:us-east-1:569239323358:textract-completion` |
| DB secret | `arn:aws:secretsmanager:us-east-1:569239323358:secret:ocr-pipeline/db-credentials-7dbJsg` |

## Security notes

- **db-init `DB_PASSWORD`**: plaintext password is set directly in the Lambda env var. Rotate and replace with `DB_SECRET_ARN` (the same pattern used by the other two Lambdas).
- **RDS encryption**: `storage_encrypted = false` on the live cluster. Enabling requires cluster replacement.
- `deletion_protection = false` and `prevent_destroy = true` (Terraform lifecycle) — the latter is the only guard against accidental cluster deletion right now.
- Follow least-privilege IAM: each Lambda role should only hold the permissions it actually exercises.
