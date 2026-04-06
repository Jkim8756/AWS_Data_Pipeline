# PDF data pipeline

## Project overview
Serverless AWS pipeline that ingests handwritten PDFs, extracts text via AWS Textract, cleans and verifies results, and stores them in RDS Postgres. High volume: thousands of PDFs per day.

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
- **DB instance identifier:** `database-1`
- **DB host:** `database-1.cr8owmsee0em.us-east-2.rds.amazonaws.com`

## Dev environment
- **OS:** Windows — use PowerShell, not bash
- **Venv activate:** `.venv\Scripts\activate` (not `source .venv/bin/activate`)
- **SSL cert:** `global-bundle.pem` lives in project root, gitignored
- **Set env vars in PowerShell:** `$env:DB_PASSWORD="value"`
- **Local SSL cert path:** `./global-bundle.pem` (scripts); Lambda deployed path: `/opt/python/global-bundle.pem`

## Repo structure
```
project/
├── CLAUDE.md
├── lambdas/
│   ├── ingest/handler.py
│   ├── process/handler.py
│   ├── clean/handler.py
│   └── write/handler.py
├── shared/
│   └── utils.py          # DB connection, shared helpers
├── scripts/
│   └── test_db_connection.py # run locally to verify RDS connectivity
├── docs/
│   └── architecture.md   # detailed decisions, not loaded every session
├── .env                  # gitignored — copy from .env.example
├── .env.example
├── global-bundle.pem     # gitignored — RDS SSL cert
└── requirements.txt
```

## Environment variables (never hardcode)
- `CONFIDENCE_THRESHOLD` — OCR confidence cutoff (start at 1.0, tune later)
- `S3_UPLOAD_BUCKET` — `timesheets-pdf-uploads-01`
- `S3_RAW_JSON_BUCKET` — `timesheet-scanned-raw-json01`
- `SQS_PROCESS_QUEUE_URL` — main processing queue
- `SQS_REVIEW_QUEUE_URL` — low-confidence review queue
- `SQS_DLQ_URL` — dead letter queue
- `DB_HOST` — `database-1.cr8owmsee0em.us-east-2.rds.amazonaws.com`
- `DB_PORT` — `5432`
- `DB_NAME` — `pdf_pipeline`
- `DB_USER` — `postgres`
- `DB_PASSWORD` — from Secrets Manager (`rds!db-...`)

## RDS schema conventions
- All tables use `snake_case`
- Every document row must have a `status` field: `pending | processing | needs_review | auto_accepted | approved | done | failed`
- Store `confidence_score` (float) and `textract_job_id` alongside extracted text

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
- Do not commit `.env` files or `global-bundle.pem`
- Do not use bash scripts on Windows — use PowerShell equivalents
