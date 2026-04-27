"""
Lambda: write
Triggered by SQS (review queue, post-approval) or called directly from clean Lambda.
Writes approved/auto-accepted records to RDS Postgres.
"""
import json
import os
import boto3
from shared.utils import get_db_connection


def lambda_handler(event: dict, context) -> dict:
    try:
        for record in event.get("Records", []):
            body = json.loads(record["body"])
            job_id: str = body["job_id"]
            s3_bucket: str = body["s3_bucket"]
            s3_key: str = body["s3_key"]
            confidence: float = float(body["confidence"])
            text: str = body["text"]

            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE documents
                        SET status = 'approved',
                            extracted_text = %s,
                            confidence_score = %s
                        WHERE textract_job_id = %s
                        """,
                        (text, confidence, job_id),
                    )
                conn.commit()
                print(f"Updated document {job_id} to approved")
            finally:
                conn.close()
        return {"statusCode": 200}
    except Exception as e:
        print(f"ERROR in write: {e}")
        raise
