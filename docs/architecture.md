# Architecture decisions

## Pipeline flow

1. **S3 upload** — PDFs land in `timesheets-pdf-uploads-01`. S3 event notification triggers the ingest Lambda.
2. **Ingest Lambda** — Validates the event and enqueues an SQS message to `SQS_PROCESS_QUEUE_URL`. No Textract calls here; keeps ingest fast and decoupled.
3. **Process Lambda** — Reads from the process queue. Calls `textract.start_document_text_detection` (async). Textract publishes completion to an SNS topic when done.
4. **Clean Lambda** — Subscribed to the Textract SNS topic. Fetches full results, computes mean word confidence, extracts plain text. Always writes raw JSON to `S3_RAW_JSON_BUCKET`. Routes based on `CONFIDENCE_THRESHOLD`:
   - **≥ threshold** → writes directly to RDS with status `auto_accepted`
   - **< threshold** → enqueues to `SQS_REVIEW_QUEUE_URL` and writes to RDS with status `needs_review`
5. **Write Lambda** — Processes the review queue after a human approves. Updates the RDS row to `approved`.

## RDS schema (documents table)

```sql
CREATE TABLE documents (
    id                SERIAL PRIMARY KEY,
    textract_job_id   TEXT UNIQUE NOT NULL,
    s3_bucket         TEXT NOT NULL,
    s3_key            TEXT NOT NULL,
    confidence_score  FLOAT,
    extracted_text    TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Key decisions

- **Async Textract** — synchronous mode has a 5-page / 5 MB limit; async handles large handwritten timesheets.
- **SQS between ingest and process** — decouples upload spikes from Textract throughput; DLQ catches poison messages.
- **Raw JSON always to S3** — preserves original Textract output for reprocessing or auditing without re-running OCR.
- **Confidence threshold env var** — start at 1.0 (everything reviewed) and lower as the model's accuracy is validated.
- **SSL verify-full** — all RDS connections require the AWS global bundle cert; cert path differs between local (`./global-bundle.pem`) and Lambda (`/opt/python/global-bundle.pem`).
