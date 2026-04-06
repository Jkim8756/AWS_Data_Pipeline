"""
Lambda: ingest
Triggered by S3 PUT on the upload bucket.
Enqueues a message to SQS for downstream processing.
"""
import json
import os
import boto3


sqs = boto3.client("sqs", region_name="us-east-2")


def lambda_handler(event: dict, context) -> dict:
    try:
        queue_url = os.environ["SQS_PROCESS_QUEUE_URL"]
        for record in event.get("Records", []):
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]
            message = {"bucket": bucket, "key": key}
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message),
            )
            print(f"Enqueued s3://{bucket}/{key}")
        return {"statusCode": 200}
    except Exception as e:
        print(f"ERROR in ingest: {e}")
        raise
