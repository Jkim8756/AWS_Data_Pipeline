"""
Lambda: ocr_trigger
Triggered by S3 PutObject on the PDF uploads bucket.
Starts an async Textract document analysis job and logs the job ID.
No DB writes — source file info travels with the Textract SNS notification.
"""
import logging
import os
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")


def lambda_handler(event: dict, context) -> dict:
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        try:
            response = textract.start_document_analysis(
                DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
                FeatureTypes=["TABLES", "FORMS"],
                NotificationChannel={
                    "SNSTopicArn": os.environ["TEXTRACT_SNS_TOPIC_ARN"],
                    "RoleArn": os.environ["TEXTRACT_ROLE_ARN"],
                },
            )
            job_id = response["JobId"]
            logger.info("Started Textract job %s for s3://%s/%s", job_id, bucket, key)
        except Exception as e:
            logger.error("Failed to start Textract job for %s: %s", key, e)
            raise

    return {"statusCode": 200}
