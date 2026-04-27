import os
import re
from urllib.parse import unquote_plus

import boto3


textract = boto3.client("textract", region_name="us-east-1")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
TEXTRACT_ROLE_ARN = os.environ["TEXTRACT_ROLE_ARN"]


def lambda_handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        if not key.lower().endswith(".pdf"):
            print(f"Skipping non-PDF key: {key}")
            continue

        # Textract JobTag only allows [a-zA-Z0-9_.\-:] — sanitize filename
        job_tag = re.sub(r"[^a-zA-Z0-9_.\-:]", "_", key)[:128]

        print(f"Starting Textract job for s3://{bucket}/{key}  JobTag={job_tag}")
        response = textract.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
            NotificationChannel={
                "SNSTopicArn": SNS_TOPIC_ARN,
                "RoleArn": TEXTRACT_ROLE_ARN,
            },
            JobTag=job_tag,
        )
        print(f"Textract JobId: {response['JobId']}")

    return {"statusCode": 200, "body": "Textract job(s) started"}
