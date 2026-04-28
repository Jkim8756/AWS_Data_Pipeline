import json
import os

import boto3
import psycopg2


def get_db_conn():
    secret = json.loads(
        boto3.client("secretsmanager")
        .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    # Secret only holds credentials; host/dbname come from env vars
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "ocrdb"),
        user=secret["username"],
        password=secret["password"],
    )


DDL = """
CREATE TABLE IF NOT EXISTS document_pages (
    id             SERIAL PRIMARY KEY,
    file_name      TEXT          NOT NULL,
    s3_key         TEXT          NOT NULL,
    s3_bucket      TEXT          NOT NULL,
    job_id         TEXT,
    page_number    INTEGER       NOT NULL,
    extracted_text TEXT,
    word_count     INTEGER,
    confidence_avg NUMERIC(5,2),
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (s3_key, page_number)
);

CREATE INDEX IF NOT EXISTS idx_doc_pages_s3_key ON document_pages(s3_key);
CREATE INDEX IF NOT EXISTS idx_doc_pages_job_id ON document_pages(job_id);
"""


def lambda_handler(event, context):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
        return {"statusCode": 200, "body": "Schema applied successfully"}
    finally:
        conn.close()
