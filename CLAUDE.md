# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview
Serverless AWS pipeline that ingests handwritten PDF timesheets, extracts text via AWS Textract (async, table + form analysis), cleans and structures the results, and stores them in Aurora PostgreSQL. High volume: thousands of PDFs per day.

## Architecture

Two Lambda functions form the active pipeline (deployed via CDK in `infra/`):

```
S3 (PDF upload)
    → ocr_trigger Lambda    (insert documents row, start async Textract job)
    → SNS textract-completion topic
    → ocr_processor Lambda  (fetch blocks, parse tables, write work_entries + update documents)
```

Older hand-rolled Lambdas (`lambdas/ingest`, `lambdas/process`, `lambdas/clean`, `lambdas/write`) represent a prior architecture with an SQS-based routing stage and a separate confidence-based review queue. They are not wired into the CDK stack.

## Dev environment
- **OS:** Windows — use PowerShell, not bash
- **Venv activate:** `.venv\Scripts\activate`
- **Env vars:** loaded via `python-dotenv` from `.env` (copy from `.env.example`)
- **SSL cert:** `global-bundle.pem` in project root (gitignored); Lambda path: `/opt/python/global-bundle.pem`

## Common commands (PowerShell)

```powershell
# Install root deps (boto3, psycopg2, dotenv)
pip install -r requirements.txt

# Verify RDS connectivity locally
python scripts/test_db_connection.py

# Apply DB schema
python scripts/create_table.py

# Build psycopg2 Lambda layer (requires Docker)
bash scripts/build_layer.sh   # produces layers/psycopg2/python/...

# CDK — from infra/ directory
pip install -r infra/requirements.txt
cdk diff
cdk deploy
cdk destroy
```

## Environment variables (never hardcode)

| Variable | Value / Notes |
|---|---|
| `DB_HOST` | `db-test02.cr8owmsee0em.us-east-2.rds.amazonaws.com` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `postgres` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | from Secrets Manager (`rds!db-...`) |
| `DB_SECRET_ARN` | Secrets Manager ARN used by CDK-deployed Lambdas (replaces DB_USER/DB_PASSWORD) |
| `SSL_CERT_PATH` | `./global-bundle.pem` locally; `/opt/python/global-bundle.pem` on Lambda |
| `S3_UPLOAD_BUCKET` | `timesheets-pdf-uploads-01` |
| `S3_RAW_JSON_BUCKET` | `timesheet-scanned-raw-json01` |
| `SQS_PROCESS_QUEUE_URL` | `https://sqs.us-east-2.amazonaws.com/569239323358/pdf-process-queue` |
| `SQS_REVIEW_QUEUE_URL` | `https://sqs.us-east-2.amazonaws.com/569239323358/pdf-review-queue` |
| `SQS_WRITE_QUEUE_URL` | Write queue URL (used by `lambdas/clean`) |
| `SQS_DLQ_URL` | `https://sqs.us-east-2.amazonaws.com/569239323358/pdf-process-dlq` |
| `TEXTRACT_SNS_TOPIC_ARN` | `arn:aws:sns:us-east-2:569239323358:pdf-textract-completion` |
| `TEXTRACT_ROLE_ARN` | `arn:aws:iam::569239323358:role/pdf-textract-sns-role` (Textract service role, not Lambda execution role) |
| `CONFIDENCE_THRESHOLD` | OCR confidence cutoff (start at 1.0, tune later) |

## DB schema (db/schema.sql)

Three tables — all use `snake_case`, UUIDs as PKs:

- **`documents`** — one row per uploaded PDF; tracks `filename`, `s3_key`, `s3_bucket`, `textract_job_id`, `job_status` (`PENDING | SUBMITTED | SUCCEEDED | FAILED`)
- **`pages`** — per-page OCR metadata (confidence stats, block counts); FK to `documents`
- **`work_entries`** — structured employee rows parsed from timesheet tables; FK to `documents`; fields include `work_date`, `project`, `business_unit`, `staff_type`, `employee_name`, `ein`, scheduled/actual times, `hours_worked`, `absent`

> `docs/architecture.md` contains an older single-table schema — `db/schema.sql` is authoritative.

## CDK infrastructure (infra/)

`infra/stacks/ocr_pipeline_stack.py` provisions the full stack:
- VPC (2 AZs, 1 NAT GW), Lambda SG, Aurora SG
- Secrets Manager secret for DB credentials
- Aurora PostgreSQL Serverless v2 (engine 15.4) in private subnets
- S3 input bucket (event notification → `ocr-trigger` Lambda on `*.pdf`)
- SNS topic `textract-completion` → `ocr-processor` Lambda subscription
- IAM roles with least-privilege policies for each Lambda
- Lambda Layer (`layers/psycopg2`) — must be built with `scripts/build_layer.sh` before deploying

## Lambda architecture details

**`ocr_trigger`** (`lambdas/ocr_trigger/handler.py`):
- Triggered by S3 `OBJECT_CREATED` events
- Inserts a `documents` row; starts `textract.start_document_analysis` with `TABLES` + `FORMS` feature types
- Uses `JobTag` = `document_id` to correlate the async callback
- Gets DB credentials from Secrets Manager via `DB_SECRET_ARN`

**`ocr_processor`** (`lambdas/ocr_processor/handler.py`):
- Triggered by SNS Textract completion notification
- Paginates `get_document_analysis` blocks; detects staff type (FRONTLINE vs MANAGEMENT) by finding the nearest section header above each table
- Extracts header fields (Project, Business Unit, Date) from `KEY_VALUE_SET` blocks
- Writes one `work_entries` row per employee per table; updates `documents.job_status` to `SUCCEEDED`

**`shared/utils.py`** — `get_db_connection()` using `DB_USER`/`DB_PASSWORD` + `sslmode=verify-full` + `global-bundle.pem`. CDK Lambdas have their own inline `get_db_connection()` that reads from Secrets Manager instead.

## AWS setup
- **Region:** us-east-2 (Ohio)
- **Runtime:** Python 3.12
- **IAM:** Admin0 user; Lambdas use dedicated least-privilege execution roles
- **DB instance (manual):** `db-test02` at `db-test02.cr8owmsee0em.us-east-2.rds.amazonaws.com` (RDS Postgres 17.4)
- **DB cluster (CDK):** Aurora Serverless v2, default DB name `ocrdb`, credentials from `ocr-pipeline/db-credentials` secret

## Python conventions
- Use `boto3` for all AWS SDK calls
- Wrap all Lambda handlers in `try/except` — never let exceptions bubble silently
- Log with `print()` to stdout (CloudWatch picks this up automatically)
- Keep each Lambda under 250 lines — move shared logic to `shared/utils.py`
- Use type hints on all function signatures

## What NOT to do
- Do not hardcode credentials, ARNs, or bucket names — use environment variables
- Do not store PDFs in RDS — S3 only
- Do not call Textract synchronously for multi-page PDFs — always use async (`start_document_analysis`)
- Do not commit `.env` or `global-bundle.pem`
- Do not use bash on Windows — use PowerShell equivalents
