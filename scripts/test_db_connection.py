"""
Run locally to verify RDS connectivity.
Requires .env to be loaded or env vars set in PowerShell.

Usage (PowerShell):
    $env:DB_PASSWORD="your-password"
    $env:SSL_CERT_PATH="./global-bundle.pem"
    python scripts/test_db_connection.py
"""
import os
import sys

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.utils import get_db_connection

os.environ.setdefault("SSL_CERT_PATH", "./global-bundle.pem")
os.environ.setdefault("DB_HOST", "database-1.cr8owmsee0em.us-east-2.rds.amazonaws.com")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "pdf_pipeline")
os.environ.setdefault("DB_USER", "postgres")


def main() -> None:
    print("Connecting to RDS...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()
            print(f"Connected. Postgres version: {version[0]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
