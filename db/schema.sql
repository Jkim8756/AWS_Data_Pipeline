CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tracks each PDF uploaded to S3 and its Textract processing state
CREATE TABLE IF NOT EXISTS documents (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    filename         TEXT        NOT NULL,
    s3_key           TEXT        NOT NULL,
    s3_bucket        TEXT        NOT NULL,
    upload_time      TIMESTAMPTZ NOT NULL,
    textract_job_id  TEXT        UNIQUE,
    job_status       TEXT        NOT NULL DEFAULT 'PENDING',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(textract_job_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(job_status);

-- Stores per-page OCR metadata extracted by Textract for each document
CREATE TABLE IF NOT EXISTS pages (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number      INTEGER     NOT NULL,
    total_blocks     INTEGER     NOT NULL DEFAULT 0,
    word_count       INTEGER     NOT NULL DEFAULT 0,
    line_count       INTEGER     NOT NULL DEFAULT 0,
    avg_confidence   NUMERIC(5,2),
    min_confidence   NUMERIC(5,2),
    max_confidence   NUMERIC(5,2),
    page_text        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_pages_document_id ON pages(document_id);

-- Structured employee work entries extracted from daily declaration forms
CREATE TABLE IF NOT EXISTS work_entries (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      UUID        REFERENCES documents(id) ON DELETE CASCADE,
    source_file      TEXT        NOT NULL,
    work_date        DATE,
    project          TEXT,
    business_unit    TEXT,
    staff_type       TEXT,
    job_task         TEXT,
    title            TEXT,
    employee_name    TEXT,
    ein              TEXT,
    scheduled_start  TEXT,
    scheduled_end    TEXT,
    scheduled_hours  NUMERIC(5,2),
    actual_start     TEXT,
    lunch_out        TEXT,
    lunch_in         TEXT,
    actual_end       TEXT,
    hours_worked     NUMERIC(5,2),
    absent           BOOLEAN      DEFAULT FALSE,
    page_number      INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_work_entries_document_id ON work_entries(document_id);
CREATE INDEX IF NOT EXISTS idx_work_entries_work_date   ON work_entries(work_date);
CREATE INDEX IF NOT EXISTS idx_work_entries_employee    ON work_entries(employee_name);
