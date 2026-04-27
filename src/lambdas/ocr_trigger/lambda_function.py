import os
import urllib.parse

import boto3


textract = boto3.client("textract")

SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
TEXTRACT_ROLE_ARN = os.environ["TEXTRACT_ROLE_ARN"]


def lambda_handler(event, context):
    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

    if not key.lower().endswith(".pdf"):
        return

    response = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        NotificationChannel={
            "SNSTopicArn": SNS_TOPIC_ARN,
            "RoleArn": TEXTRACT_ROLE_ARN,
        },
    )

    print(f"Started Textract job {response['JobId']} for s3://{bucket}/{key}")
    return {"jobId": response["JobId"]}
