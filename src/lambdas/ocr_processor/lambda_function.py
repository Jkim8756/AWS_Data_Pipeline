import json
import os
from collections import defaultdict

import boto3
import psycopg2
import psycopg2.extras


textract = boto3.client("textract")


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


def get_all_blocks(job_id):
    blocks = []
    kwargs = {"JobId": job_id}
    while True:
        response = textract.get_document_text_detection(**kwargs)
        blocks.extend(response.get("Blocks", []))
        next_token = response.get("NextToken")
        if not next_token:
            break
        kwargs["NextToken"] = next_token
    return blocks


def group_lines_by_page(blocks):
    pages = defaultdict(list)
    for block in blocks:
        if block.get("BlockType") == "LINE":
            pages[block.get("Page", 1)].append(block)
    # Sort each page's lines top-to-bottom by vertical position
    for page_num in pages:
        pages[page_num].sort(key=lambda b: b.get("Geometry", {}).get("BoundingBox", {}).get("Top", 0))
    return pages


def lambda_handler(event, context):
    message = json.loads(event["Records"][0]["Sns"]["Message"])
    status = message.get("Status")
    job_id = message.get("JobId")
    doc_location = message.get("DocumentLocation", {})
    s3_bucket = doc_location.get("S3Bucket", "")
    s3_key = doc_location.get("S3ObjectName", "")

    if status != "SUCCEEDED":
        print(f"Textract job {job_id} ended with status {status} — skipping")
        return

    file_name = s3_key.split("/")[-1]
    blocks = get_all_blocks(job_id)
    pages = group_lines_by_page(blocks)

    rows = []
    for page_num, line_blocks in sorted(pages.items()):
        texts = [b.get("Text", "") for b in line_blocks]
        confidences = [b.get("Confidence", 0.0) for b in line_blocks]
        extracted_text = "\n".join(texts)
        word_count = len(extracted_text.split())
        confidence_avg = round(sum(confidences) / len(confidences), 2) if confidences else None
        rows.append((file_name, s3_key, s3_bucket, job_id, page_num, extracted_text, word_count, confidence_avg))

    if not rows:
        print(f"No LINE blocks found for job {job_id}")
        return

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO document_pages
                        (file_name, s3_key, s3_bucket, job_id, page_number, extracted_text, word_count, confidence_avg)
                    VALUES %s
                    ON CONFLICT (s3_key, page_number) DO UPDATE SET
                        extracted_text = EXCLUDED.extracted_text,
                        word_count     = EXCLUDED.word_count,
                        confidence_avg = EXCLUDED.confidence_avg,
                        job_id         = EXCLUDED.job_id
                    """,
                    rows,
                )
        print(f"Inserted {len(rows)} page(s) for {file_name} (job {job_id})")
    finally:
        conn.close()
