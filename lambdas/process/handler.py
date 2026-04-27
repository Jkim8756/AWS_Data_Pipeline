"""
Lambda: process
Triggered by SQS (process queue).
Starts an async Textract job for each PDF.
"""
import json
import os
import boto3


textract = boto3.client("textract", region_name="us-east-2")


def lambda_handler(event: dict, context) -> dict:
    try:
        for record in event.get("Records", []):
            body = json.loads(record["body"])
            bucket: str = body["bucket"]
            key: str = body["key"]

            response = textract.start_document_analysis(
                DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
                FeatureTypes=["TABLES", "FORMS"],
                NotificationChannel={
                    "SNSTopicArn": os.environ["TEXTRACT_SNS_TOPIC_ARN"],
                    "RoleArn": os.environ["TEXTRACT_ROLE_ARN"],
                },
                JobTag=key,
            )
            job_id = response["JobId"]
            print(f"Started Textract job {job_id} for s3://{bucket}/{key}")
        return {"statusCode": 200}
    except Exception as e:
        print(f"ERROR in process: {e}")
        raise
