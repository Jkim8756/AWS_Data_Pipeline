import json
import os

import boto3
import psycopg2
import psycopg2.extras


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


def lambda_handler(event, context):
    file_name = event.get("file_name")
    limit = int(event.get("limit", 50))

    where_clause = "WHERE file_name = %s" if file_name else ""
    params = [file_name] if file_name else []
    params.append(limit)

    conn = get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    file_name,
                    page_number,
                    word_count,
                    confidence_avg,
                    created_at::text,
                    extracted_text
                FROM document_pages
                {where_clause}
                ORDER BY file_name, page_number
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
        return {
            "statusCode": 200,
            "count": len(rows),
            "rows": [dict(r) for r in rows],
        }
    finally:
        conn.close()
