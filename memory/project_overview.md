---
name: PDF pipeline project overview
description: Serverless AWS pipeline for ingesting handwritten PDFs via Textract into RDS Postgres
type: project
---

Serverless PDF data pipeline on AWS (us-east-2). Ingests handwritten PDFs, extracts text via Textract, and stores in RDS Postgres (database-1, pdf_pipeline DB).

**Why:** High-volume timesheet processing (thousands of PDFs/day) with human review for low-confidence OCR results.

**How to apply:** All new Lambdas follow the same patterns — env vars only (no hardcoded ARNs/creds), try/except wrapping, print() logging, shared/utils.py for DB, under 250 lines each.

Key env vars: CONFIDENCE_THRESHOLD (start 1.0), S3_UPLOAD_BUCKET, S3_RAW_JSON_BUCKET, SQS_PROCESS_QUEUE_URL, SQS_REVIEW_QUEUE_URL, DB_* vars.

Pipeline: S3 → ingest Lambda → SQS → process Lambda → Textract → SNS → clean Lambda → (auto-accept to RDS | review queue → write Lambda → RDS). Raw JSON always written to S3.
