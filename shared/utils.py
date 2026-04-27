import os
import psycopg2
from psycopg2.extensions import connection as PgConnection


def get_db_connection() -> PgConnection:
    """Return a psycopg2 connection to RDS Postgres using env vars."""
    ssl_cert = os.environ.get("SSL_CERT_PATH", "/opt/python/global-bundle.pem")
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode="verify-full",
        sslrootcert=ssl_cert,
    )
