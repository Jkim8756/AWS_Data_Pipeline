"""
Production trigger: polls an SQS queue for S3 ObjectCreated events.

Replaces watcher.py in ECS Fargate deployments.

Message flow:
  S3 ObjectCreated:*.pdf
      → SQS queue (S3 event notification)
      → this worker: downloads PDF from S3, runs processor.py, deletes message

On failure the message becomes visible again after the queue's
visibility timeout — built-in retry with no extra code.

Run with:
    python sqs_worker.py
"""
import json
import logging
import os
import tempfile
from pathlib import Path

import boto3

from db.migrations import run_migrations
from processor import process_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

SQS_QUEUE_URL = os.environ["SQS_QUEUE_URL"]
POLL_WAIT_SECONDS = int(os.environ.get("POLL_WAIT_SECONDS", "20"))  # long-poll
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", "1"))

sqs = boto3.client("sqs")
s3 = boto3.client("s3")


def handle_message(body: dict) -> None:
    """
    Parse an S3 event notification and process the PDF.

    S3 sends either a direct S3Event or wraps it in an SNS envelope;
    we handle both.
    """
    # Unwrap SNS envelope if present
    if "Message" in body:
        body = json.loads(body["Message"])

    records = body.get("Records", [])
    for record in records:
        s3_info = record.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name")
        key = s3_info.get("object", {}).get("key", "").replace("+", " ")

        if not bucket or not key:
            log.warning("Skipping record — missing bucket or key: %s", record)
            continue

        if not key.lower().endswith(".pdf"):
            log.info("Skipping non-PDF object: s3://%s/%s", bucket, key)
            continue

        log.info("Downloading s3://%s/%s", bucket, key)
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / Path(key).name
            s3.download_file(bucket, key, str(local_path))
            doc_id = process_pdf(local_path, s3_bucket=bucket, s3_key=key)
            log.info("Processed s3://%s/%s → doc_id=%d", bucket, key, doc_id)


def main():
    log.info("Running migrations …")
    run_migrations()

    log.info("Polling SQS queue: %s", SQS_QUEUE_URL)
    while True:
        response = sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=MAX_MESSAGES,
            WaitTimeSeconds=POLL_WAIT_SECONDS,
            AttributeNames=["All"],
        )

        messages = response.get("Messages", [])
        if not messages:
            continue  # long-poll timeout, loop again

        for msg in messages:
            receipt_handle = msg["ReceiptHandle"]
            try:
                body = json.loads(msg["Body"])
                handle_message(body)
                # Delete only on success — failure leaves message visible for retry
                sqs.delete_message(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=receipt_handle,
                )
            except Exception:
                log.exception("Error handling SQS message — will retry after visibility timeout")


if __name__ == "__main__":
    main()
