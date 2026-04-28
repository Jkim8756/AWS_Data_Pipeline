"""
Idempotent schema setup.  Run once on startup or manually.

Tables
------
documents       — one row per PDF file (deduped by file_hash)
document_pages  — one row per page, with raw text + structured JSONB
"""
from .connection import get_conn

DDL = """
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL PRIMARY KEY,
    file_name    TEXT        NOT NULL,
    file_hash    TEXT        NOT NULL,
    s3_bucket    TEXT,
    s3_key       TEXT,
    page_count   INTEGER,
    ocr_model    TEXT        NOT NULL DEFAULT 'claude',
    status       TEXT        NOT NULL DEFAULT 'pending',
    error_msg    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (file_hash)
);

CREATE TABLE IF NOT EXISTS document_pages (
    id               SERIAL PRIMARY KEY,
    document_id      INTEGER     NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number      INTEGER     NOT NULL,
    extracted_text   TEXT,
    structured_data  JSONB,
    word_count       INTEGER,
    confidence       NUMERIC(5,2),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_doc_pages_document_id
    ON document_pages(document_id);

CREATE INDEX IF NOT EXISTS idx_doc_pages_structured
    ON document_pages USING gin(structured_data);

-- Auto-update updated_at on documents
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_documents_updated_at'
    ) THEN
        CREATE TRIGGER trg_documents_updated_at
        BEFORE UPDATE ON documents
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END;
$$;
"""


def run_migrations():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
        print("Migrations applied successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
