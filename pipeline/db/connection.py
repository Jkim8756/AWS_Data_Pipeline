"""
Database connection helper.

Supports two credential modes:
  - Local dev: DATABASE_URL env var  (postgres://user:pass@host:5432/dbname)
  - AWS (ECS/Lambda): DB_SECRET_ARN + DB_HOST + DB_NAME env vars
"""
import json
import os

import psycopg2
import psycopg2.extras


def get_conn():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    # AWS path: credentials from Secrets Manager, host/dbname from env vars
    import boto3

    secret = json.loads(
        boto3.client("secretsmanager")
        .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "ocrdb"),
        user=secret["username"],
        password=secret["password"],
    )
