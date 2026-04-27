import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.utils import get_db_connection

sql = """
CREATE TABLE IF NOT EXISTS documents (
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
"""

conn = get_db_connection()
try:
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print("Table created successfully.")
finally:
    conn.close()