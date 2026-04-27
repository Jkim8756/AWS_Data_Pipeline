import json
import logging
import os
from urllib.parse import unquote_plus

import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")
secretsmanager = boto3.client("secretsmanager")


def get_db_connection():
    secret = json.loads(
        secretsmanager.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])[
            "SecretString"
        ]
    )
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        dbname=os.environ["DB_NAME"],
        user=secret["username"],
        password=secret["password"],
        sslmode="require",
        connect_timeout=5,
    )


def lambda_handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        upload_time = record["eventTime"]
        filename = key.split("/")[-1]

        conn = get_db_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO documents
                            (filename, s3_key, s3_bucket, upload_time, job_status)
                        VALUES (%s, %s, %s, %s, 'PENDING')
                        ON CONFLICT DO NOTHING
                        RETURNING id
                        """,
                        (filename, key, bucket, upload_time),
                    )
                    row = cur.fetchone()

            if row is None:
                logger.info("Skipping duplicate S3 event for key: %s", key)
                continue

            document_id = str(row[0])

            response = textract.start_document_analysis(
                DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
                FeatureTypes=["TABLES", "FORMS"],
                NotificationChannel={
                    "SNSTopicArn": os.environ["TEXTRACT_SNS_TOPIC_ARN"],
                    "RoleArn": os.environ["TEXTRACT_ROLE_ARN"],
                },
                JobTag=document_id,
            )
            job_id = response["JobId"]

            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE documents
                        SET textract_job_id = %s, job_status = 'SUBMITTED'
                        WHERE id = %s
                        """,
                        (job_id, document_id),
                    )

            logger.info("Started Textract job %s for document %s", job_id, document_id)

        finally:
            conn.close()
