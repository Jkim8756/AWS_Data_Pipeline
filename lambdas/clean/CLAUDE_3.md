# PDF data pipeline

## Project overview
Serverless AWS pipeline that ingests handwritten timesheets as PDFs, extracts text via AWS Textract, cleans and verifies results, and stores them in RDS Postgres. High volume: thousands of PDFs per day.

## Architecture
```
S3 (upload) → Lambda ingest → SQS → Lambda process → Textract
                                                          ↓
                                              Lambda clean + verify
                                                ↙            ↘
                                         high confidence   low confidence
                                              ↓                  ↓
                                        Lambda write       SQS review queue → human reviewer
                                              ↓                  ↓
                                        RDS Postgres        RDS Postgres (after approval)
                                              ↓
                                        S3 raw JSON (always written, regardless of path)
```

## AWS setup
- **Region:** us-east-2 (Ohio)
- **Runtime:** Python 3.12
- **IAM:** Admin0 user. Lambdas use a dedicated least-privilege execution role.
- **DB:** RDS Postgres 17.4 — connection details in environment variables, never hardcoded
- **DB instance identifier:** `db-test02`
- **DB host:** `db-test02.cr8owmsee0em.us-east-2.rds.amazonaws.com`

## Dev environment
- **OS:** Windows — use PowerShell, not bash
- **Env vars:** loaded via `python-dotenv` — keep `.env` file up to date
- **Venv activate:** `.venv\Scripts\activate`
- **SSL cert:** `global-bundle.pem` lives in project root, gitignored
- **Local SSL cert path:** `./global-bundle.pem` (scripts); Lambda deployed path: `/opt/python/global-bundle.pem`

## Repo structure
```
project/
├── CLAUDE.md
├── lambdas/
│   ├── ingest/
│   │   ├── handler.py
│   │   └── vendor/           ← aws-psycopg2 + python-dotenv installed here
│   ├── process/
│   │   ├── handler.py
│   │   └── vendor/
│   ├── clean/
│   │   ├── handler.py
│   │   └── vendor/
│   └── write/
│       ├── handler.py
│       └── vendor/
├── shared/
│   └── utils.py              ← DB connection, schema creation, row mapping
├── scripts/
│   ├── migrate.sql           ← Run once to create RDS tables
│   └── test_db_connection.py ← Run locally to verify RDS connectivity
├── .env                      ← gitignored
├── .env.example
├── global-bundle.pem         ← gitignored
└── requirements.txt
```

## Environment variables (never hardcode)
- `CONFIDENCE_THRESHOLD` — OCR confidence cutoff (default 0.75)
- `S3_UPLOAD_BUCKET` — `timesheets-pdf-uploads-01`
- `S3_RAW_JSON_BUCKET` — `timesheet-scanned-raw-json01`
- `SQS_PROCESS_QUEUE_URL` — `https://sqs.us-east-2.amazonaws.com/569239323358/pdf-process-queue`
- `SQS_REVIEW_QUEUE_URL` — `https://sqs.us-east-2.amazonaws.com/569239323358/pdf-review-queue`
- `SQS_DLQ_URL` — `https://sqs.us-east-2.amazonaws.com/569239323358/pdf-process-dlq`
- `TEXTRACT_SNS_TOPIC_ARN` — `arn:aws:sns:us-east-2:569239323358:pdf-textract-completion`
- `TEXTRACT_ROLE_ARN` — `arn:aws:iam::569239323358:role/pdf-textract-sns-role`
- `SSL_CERT_PATH` — `./global-bundle.pem` locally; `/opt/python/global-bundle.pem` on Lambda
- `DB_HOST` — `db-test02.cr8owmsee0em.us-east-2.rds.amazonaws.com`
- `DB_PORT` — `5432`
- `DB_NAME` — `postgres`
- `DB_USER` — `postgres`
- `DB_PASSWORD` — from Secrets Manager

## RDS schema
- Tables: `timesheet_documents`, `timesheet_records`
- All tables use `snake_case`
- Status values: `pending | processing | needs_review | auto_accepted | approved | done | failed`
- Key fields: `confidence_score` (float), `textract_job_id`, `raw_json_s3_key`

## Lambda deployment — CRITICAL RULES

### psycopg2 must be vendored inside each Lambda zip
**Never use a Lambda layer for psycopg2.** pip on Windows always installs the wrong
platform binary. The only reliable method is:

1. Download the pure-Python wheel from PyPI:
   ```powershell
   pip download aws-psycopg2==1.3.8 --no-deps --dest ./wheels
   ```

2. Rename to `.zip` and extract manually (do NOT use pip install):
   ```powershell
   Copy-Item ./wheels/aws_psycopg2-1.3.8-py3-none-any.whl ./wheels/aws_psycopg2.zip
   Expand-Archive -Path ./wheels/aws_psycopg2.zip -DestinationPath ./vendor -Force
   ```

3. Verify — must show only `.py` files, NO `.pyd` or `.dylib`:
   ```powershell
   Get-ChildItem ./vendor/psycopg2 -Name
   ```

4. Each `handler.py` must have this at the very top before all imports:
   ```python
   import sys, os
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))
   ```

### Zip structure required by Lambda
Each Lambda zip must contain at the root level:
- `handler.py`
- `shared/` (copy of the shared/ folder)
- `vendor/` (psycopg2 + python-dotenv)

Build each zip from inside the Lambda's folder:
```powershell
cd lambdas/clean
Compress-Archive -Path handler.py, shared, vendor -DestinationPath ../../clean.zip -Force
cd ../..
```

Repeat for `ingest`, `process`, `write`.

### Lambda handler entry points
| Lambda | Handler setting in console |
|--------|---------------------------|
| ingest | `handler.handler` |
| process | `handler.handler` |
| clean | `handler.handler` |
| write | `handler.handler` |

### AWS trigger wiring
| Lambda | Trigger |
|--------|---------|
| ingest | S3 → `timesheets-pdf-uploads-01`, event `s3:ObjectCreated:*`, suffix `.pdf` |
| process | SQS → `pdf-process-queue`, batch size 1 |
| clean | SNS → `pdf-textract-completion` |
| write | SQS → `pdf-process-queue` (high-confidence path) |

### SNS → clean Lambda subscription (must be done manually)
The clean Lambda will never fire unless it is subscribed to the SNS topic AND has a resource policy allowing SNS to invoke it. Both must be set:
```powershell
# Subscribe
aws sns subscribe `
  --topic-arn $env:TEXTRACT_SNS_TOPIC_ARN `
  --protocol lambda `
  --notification-endpoint YOUR_CLEAN_LAMBDA_ARN

# Grant invoke permission
aws lambda add-permission `
  --function-name YOUR_CLEAN_LAMBDA_NAME `
  --statement-id sns-invoke-clean `
  --action lambda:InvokeFunction `
  --principal sns.amazonaws.com `
  --source-arn $env:TEXTRACT_SNS_TOPIC_ARN
```

### Textract service role requirements
`pdf-textract-sns-role` must have:
- **Permission:** `sns:Publish` on `pdf-textract-completion`
- **Trust relationship:** `textract.amazonaws.com` can assume the role

## Python conventions
- Use `boto3` for all AWS SDK calls
- Wrap all Lambda handlers in try/except — never let exceptions bubble silently
- Log with `print()` to stdout (CloudWatch picks this up automatically)
- Keep each Lambda under 250 lines — move shared logic to `shared/utils.py`
- Use type hints on all function signatures

## What NOT to do
- Do not hardcode credentials, ARNs, or bucket names — use environment variables
- Do not store PDFs in RDS — S3 only
- Do not call Textract directly from the ingest Lambda — always go through SQS
- Do not commit `.env`, `global-bundle.pem`, `*.zip`, `layer/`, or `vendor/` to git
- Do not use a Lambda layer for psycopg2 — vendor it inside the zip instead
- Do not use bash — use PowerShell equivalents
- Do not install psycopg2 with `pip install` on Windows — always extract the wheel manually

## .gitignore must include
```
.env
global-bundle.pem
*.zip
layer/
lambdas/*/vendor/
lambdas/*/wheels/
__pycache__/
*.pyc
```
