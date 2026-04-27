import json
import logging
import os
from datetime import datetime

import boto3
import psycopg2

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")
secretsmanager = boto3.client("secretsmanager")

# Column index → field name for the employee roster table
COL_MAP = {
    2: "job_task",
    3: "title",
    4: "employee_name",
    5: "ein",
    6: "scheduled_start",
    7: "scheduled_end",
    8: "scheduled_hours",
    9: "actual_start",
    10: "lunch_out",
    11: "lunch_in",
    12: "actual_end",
    13: "hours_worked",
    15: "absent",
}


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


def get_all_blocks(job_id: str) -> list:
    blocks = []
    next_token = None
    while True:
        kwargs = {"JobId": job_id}
        if next_token:
            kwargs["NextToken"] = next_token
        resp = textract.get_document_analysis(**kwargs)
        if resp["JobStatus"] == "FAILED":
            raise RuntimeError(f"Textract job {job_id} failed")
        blocks.extend(resp.get("Blocks", []))
        next_token = resp.get("NextToken")
        if not next_token:
            break
    return blocks


def get_cell_text(cell: dict, block_map: dict) -> str:
    words = []
    for rel in cell.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                child = block_map.get(cid)
                if child and child["BlockType"] == "WORD":
                    words.append(child.get("Text", ""))
    return " ".join(words).strip()


def get_table_cells(table: dict, block_map: dict) -> dict:
    cells = {}
    for rel in table.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                cell = block_map.get(cid)
                if cell and cell["BlockType"] == "CELL":
                    r, c = cell["RowIndex"], cell["ColumnIndex"]
                    cells[(r, c)] = get_cell_text(cell, block_map)
    return cells


def detect_staff_type(table: dict, blocks: list) -> str:
    """Return FRONTLINE or MANAGEMENT by finding the nearest section header above the table."""
    page = table.get("Page", 1)
    table_top = table.get("Geometry", {}).get("BoundingBox", {}).get("Top", 1)

    closest_label = "FRONTLINE"
    closest_distance = float("inf")

    for block in blocks:
        if block.get("Page") != page or block["BlockType"] != "LINE":
            continue
        text = block.get("Text", "").upper()
        if "FRONTLINE" not in text and "MANAGEMENT" not in text:
            continue
        block_top = block.get("Geometry", {}).get("BoundingBox", {}).get("Top", 0)
        if block_top < table_top:
            dist = table_top - block_top
            if dist < closest_distance:
                closest_distance = dist
                closest_label = "MANAGEMENT" if "MANAGEMENT" in text else "FRONTLINE"

    return closest_label


def extract_header(blocks: list, page: int) -> dict:
    """Extract Project, Business Unit, Date from KEY_VALUE_SET blocks on a page."""
    block_map = {b["Id"]: b for b in blocks}
    header = {}

    for block in blocks:
        if block.get("Page") != page or block["BlockType"] != "KEY_VALUE_SET":
            continue
        if "KEY" not in block.get("EntityTypes", []):
            continue

        key_words, val_words = [], []
        for rel in block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                for kid in rel["Ids"]:
                    w = block_map.get(kid)
                    if w and w["BlockType"] == "WORD":
                        key_words.append(w.get("Text", ""))
            elif rel["Type"] == "VALUE":
                for vid in rel["Ids"]:
                    vb = block_map.get(vid)
                    if vb:
                        for vrel in vb.get("Relationships", []):
                            if vrel["Type"] == "CHILD":
                                for kid in vrel["Ids"]:
                                    w = block_map.get(kid)
                                    if w and w["BlockType"] == "WORD":
                                        val_words.append(w.get("Text", ""))

        key = " ".join(key_words).strip().lower().rstrip(":")
        val = " ".join(val_words).strip()
        if key and val:
            header[key] = val

    return header


def parse_date(raw: str):
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def parse_entries(cells: dict, staff_type: str, page: int, document_id: str,
                  source_file: str, work_date, project: str, business_unit: str) -> list:
    if not cells:
        return []
    max_row = max(r for r, _ in cells.keys())
    entries = []

    for row_idx in range(2, max_row + 1):
        entry = {
            "document_id": document_id,
            "source_file": source_file,
            "work_date": work_date,
            "project": project,
            "business_unit": business_unit,
            "staff_type": staff_type,
            "page_number": page,
        }
        for col_idx, field in COL_MAP.items():
            entry[field] = cells.get((row_idx, col_idx), "").strip() or None

        if not entry.get("employee_name"):
            continue

        for field in ("scheduled_hours", "hours_worked"):
            val = entry.get(field)
            if val:
                try:
                    entry[field] = float(val.replace(",", "."))
                except ValueError:
                    entry[field] = None

        absent_raw = (entry.get("absent") or "").strip().upper()
        entry["absent"] = absent_raw in ("X", "YES", "Y", "1")

        entries.append(entry)

    return entries


def lambda_handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        job_id = message["JobId"]
        job_status = message["Status"]
        document_id = message.get("JobTag") or None

        conn = get_db_connection()
        try:
            if job_status != "SUCCEEDED":
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE documents SET job_status = 'FAILED' WHERE textract_job_id = %s",
                            (job_id,),
                        )
                logger.warning("Textract job %s status: %s", job_id, job_status)
                continue

            blocks = get_all_blocks(job_id)
            block_map = {b["Id"]: b for b in blocks}

            with conn:
                with conn.cursor() as cur:
                    if not document_id:
                        cur.execute(
                            "SELECT id, s3_key FROM documents WHERE textract_job_id = %s",
                            (job_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            logger.error("No document found for job %s", job_id)
                            continue
                        document_id = str(row[0])

                    cur.execute(
                        "SELECT filename FROM documents WHERE id = %s", (document_id,)
                    )
                    source_file = cur.fetchone()[0]

                    tables = [b for b in blocks if b["BlockType"] == "TABLE"]
                    total_entries = 0

                    for table in tables:
                        page = table.get("Page", 1)
                        cells = get_table_cells(table, block_map)
                        staff_type = detect_staff_type(table, blocks)

                        header = extract_header(blocks, page)
                        project = (
                            header.get("project") or
                            header.get("project name") or ""
                        )
                        business_unit = header.get("business unit") or header.get("bu") or ""
                        date_raw = header.get("date") or ""
                        work_date = parse_date(date_raw)

                        entries = parse_entries(
                            cells, staff_type, page, document_id,
                            source_file, work_date, project, business_unit
                        )

                        for e in entries:
                            cur.execute(
                                """
                                INSERT INTO work_entries
                                    (document_id, source_file, work_date, project,
                                     business_unit, staff_type, job_task, title,
                                     employee_name, ein, scheduled_start, scheduled_end,
                                     scheduled_hours, actual_start, lunch_out, lunch_in,
                                     actual_end, hours_worked, absent, page_number)
                                VALUES
                                    (%(document_id)s, %(source_file)s, %(work_date)s, %(project)s,
                                     %(business_unit)s, %(staff_type)s, %(job_task)s, %(title)s,
                                     %(employee_name)s, %(ein)s, %(scheduled_start)s, %(scheduled_end)s,
                                     %(scheduled_hours)s, %(actual_start)s, %(lunch_out)s, %(lunch_in)s,
                                     %(actual_end)s, %(hours_worked)s, %(absent)s, %(page_number)s)
                                """,
                                e,
                            )
                            total_entries += 1

                    cur.execute(
                        "UPDATE documents SET job_status = 'SUCCEEDED' WHERE id = %s",
                        (document_id,),
                    )

            logger.info(
                "Wrote %d work entries for document %s", total_entries, document_id
            )

        finally:
            conn.close()
