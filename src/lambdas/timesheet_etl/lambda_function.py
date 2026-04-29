import anthropic
import base64
import io
import json
import os

import boto3
import psycopg2
from pypdf import PdfReader, PdfWriter
from urllib.parse import unquote_plus

SYSTEM = """
You extract data from a single page of a daily timesheet PDF for a cleaning company.
Each page is one working day. Return ONLY a JSON object with this schema:
{
  "page_number": int,
  "project_name": str | null,
  "business_unit": str | null,
  "work_date": "YYYY-MM-DD" | null,
  "day_of_week": str | null,
  "weather": str | null,
  "entries": [
    {
      "staff_type": "FRONTLINE" | "MANAGEMENT",
      "row_number": int,
      "job_task": str | null,
      "title": str | null,
      "employee_name": str | null,
      "ein": str | null,
      "scheduled_start": str | null,
      "scheduled_end": str | null,
      "scheduled_hours": float | null,
      "actual_start": str | null,
      "lunch_out": str | null,
      "lunch_in": str | null,
      "actual_end": str | null,
      "hours_worked": float | null,
      "is_absent": bool,
      "changes_from_scheduled": bool
    }
  ]
}
Skip rows where employee_name is blank. Normalize date to YYYY-MM-DD using year 2025 as context.
"""


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    raw_bucket = os.environ["RAW_JSON_BUCKET"]

    for record in event["Records"]:
        body = json.loads(record["body"])
        for s3_rec in body.get("Records", []):
            bucket = s3_rec["s3"]["bucket"]["name"]
            key = unquote_plus(s3_rec["s3"]["object"]["key"])

            if not key.lower().endswith(".pdf"):
                continue

            pdf_bytes = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            pages = extract_pages_with_claude(pdf_bytes)
            result = {"pages": pages}

            raw_key = key.replace(".pdf", ".json")
            s3.put_object(
                Bucket=raw_bucket,
                Key=raw_key,
                Body=json.dumps(result),
                ContentType="application/json",
            )

            upsert(result, key)


def pdf_page_to_bytes(pdf_bytes: bytes, page_index: int) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def extract_pages_with_claude(pdf_bytes: bytes) -> list:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    client = anthropic.Anthropic()
    pages = []

    for i in range(total_pages):
        page_bytes = pdf_page_to_bytes(pdf_bytes, i)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.standard_b64encode(page_bytes).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": f"This is page {i + 1} of {total_pages}. Extract all timesheet data. Return JSON only.",
                    },
                ],
            }],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        page_data = json.loads(text.strip())
        page_data["page_number"] = i + 1
        pages.append(page_data)

    return pages


def get_conn():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode="require",
    )


def upsert(result: dict, s3_key: str):
    file_name = s3_key.split("/")[-1]
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO timesheet_documents (file_name, s3_key, page_count)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (s3_key) DO UPDATE SET page_count = EXCLUDED.page_count
                    RETURNING id
                    """,
                    (file_name, s3_key, len(result["pages"])),
                )
                doc_id = cur.fetchone()[0]

                for page in result["pages"]:
                    for entry in page.get("entries", []):
                        cur.execute(
                            """
                            INSERT INTO timesheet_entries (
                                document_id, s3_key, file_name,
                                page_number, project_name, business_unit,
                                work_date, day_of_week, weather,
                                staff_type, row_number, job_task, title,
                                employee_name, ein,
                                scheduled_start, scheduled_end, scheduled_hours,
                                actual_start, lunch_out, lunch_in, actual_end,
                                hours_worked, is_absent, changes_from_scheduled
                            ) VALUES (
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s,%s,%s,
                                %s,%s,%s,%s,%s,%s,%s
                            )
                            ON CONFLICT (s3_key, work_date, staff_type, row_number)
                            DO UPDATE SET
                                hours_worked = EXCLUDED.hours_worked,
                                is_absent    = EXCLUDED.is_absent,
                                actual_start = EXCLUDED.actual_start,
                                actual_end   = EXCLUDED.actual_end
                            """,
                            (
                                doc_id, s3_key, file_name,
                                page["page_number"], page.get("project_name"),
                                page.get("business_unit"), page.get("work_date"),
                                page.get("day_of_week"), page.get("weather"),
                                entry["staff_type"], entry["row_number"],
                                entry.get("job_task"), entry.get("title"),
                                entry.get("employee_name"), entry.get("ein"),
                                entry.get("scheduled_start"), entry.get("scheduled_end"),
                                entry.get("scheduled_hours"), entry.get("actual_start"),
                                entry.get("lunch_out"), entry.get("lunch_in"),
                                entry.get("actual_end"), entry.get("hours_worked"),
                                entry.get("is_absent", False),
                                entry.get("changes_from_scheduled", False),
                            ),
                        )
    finally:
        conn.close()
