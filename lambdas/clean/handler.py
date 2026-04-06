"""
Lambda: clean
Triggered by Textract SNS completion notification.
Fetches Textract results, computes confidence, and routes to write or review queue.
"""
import json
import os
import boto3
from shared.utils import get_db_connection


textract = boto3.client("textract", region_name="us-east-2")
sqs = boto3.client("sqs", region_name="us-east-2")
s3 = boto3.client("s3", region_name="us-east-2")


def _get_blocks(job_id: str) -> list[dict]:
    blocks: list[dict] = []
    paginator = textract.get_paginator("get_document_text_detection")
    for page in paginator.paginate(JobId=job_id):
        blocks.extend(page.get("Blocks", []))
    return blocks


def _compute_confidence(blocks: list[dict]) -> float:
    word_blocks = [b for b in blocks if b.get("BlockType") == "WORD"]
    if not word_blocks:
        return 0.0
    return sum(b.get("Confidence", 0.0) for b in word_blocks) / len(word_blocks)


def _extract_text(blocks: list[dict]) -> str:
    return " ".join(
        b["Text"] for b in blocks if b.get("BlockType") == "WORD" and "Text" in b
    )


def lambda_handler(event: dict, context) -> dict:
    try:
        threshold = float(os.environ.get("CONFIDENCE_THRESHOLD", 1.0))
        review_queue = os.environ["SQS_REVIEW_QUEUE_URL"]
        raw_json_bucket = os.environ["S3_RAW_JSON_BUCKET"]

        for record in event.get("Records", []):
            sns_message = json.loads(record["Sns"]["Message"])
            job_id: str = sns_message["JobId"]
            status: str = sns_message["Status"]
            s3_bucket: str = sns_message["DocumentLocation"]["S3Bucket"]
            s3_key: str = sns_message["DocumentLocation"]["S3ObjectName"]

            if status != "SUCCEEDED":
                print(f"Textract job {job_id} ended with status {status} — skipping")
                continue

            blocks = _get_blocks(job_id)
            confidence = _compute_confidence(blocks)
            text = _extract_text(blocks)

            raw_payload = {
                "job_id": job_id,
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "confidence": confidence,
                "text": text,
                "blocks": blocks,
            }

            # Always write raw JSON to S3
            raw_key = f"raw/{job_id}.json"
            s3.put_object(
                Bucket=raw_json_bucket,
                Key=raw_key,
                Body=json.dumps(raw_payload),
                ContentType="application/json",
            )
            print(f"Wrote raw JSON to s3://{raw_json_bucket}/{raw_key}")

            message = {
                "job_id": job_id,
                "s3_bucket": s3_bucket,
                "s3_key": s3_key,
                "confidence": confidence,
                "text": text,
            }

            if confidence >= threshold:
                # Route to write Lambda via direct invoke or separate queue
                _write_to_db(message, status="auto_accepted")
            else:
                sqs.send_message(
                    QueueUrl=review_queue,
                    MessageBody=json.dumps(message),
                )
                _write_to_db(message, status="needs_review")
                print(f"Sent job {job_id} to review queue (confidence={confidence:.2f})")

        return {"statusCode": 200}
    except Exception as e:
        print(f"ERROR in clean: {e}")
        raise


def _write_to_db(message: dict, status: str) -> None:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents
                    (textract_job_id, s3_bucket, s3_key, confidence_score, extracted_text, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (textract_job_id) DO UPDATE
                    SET confidence_score = EXCLUDED.confidence_score,
                        extracted_text   = EXCLUDED.extracted_text,
                        status           = EXCLUDED.status
                """,
                (
                    message["job_id"],
                    message["s3_bucket"],
                    message["s3_key"],
                    message["confidence"],
                    message["text"],
                    status,
                ),
            )
        conn.commit()
    finally:
        conn.close()
