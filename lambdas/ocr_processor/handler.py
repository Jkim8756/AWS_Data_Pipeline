"""
Lambda: ocr_processor
Triggered by SNS notification from Textract on job completion.
Parses TABLE and FORM blocks, detects column headers dynamically,
and writes one flat row per employee into timesheet_entries.
"""
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

# Normalised header text → DB field name.
# "no" appears twice (row number and schedule_changed No column),
# so we track them in order and assign the second "no" to sched_no.
HEADER_MAP = {
    "#": "row_no",
    "no": "row_no",           # first occurrence; second handled in build_col_map()
    "job task": "job_task",
    "task": "job_task",
    "title": "title",
    "employee name": "employee_name",
    "name": "employee_name",
    "ein": "ein",
    "sched start": "sched_start",
    "scheduled start": "sched_start",
    "sched end": "sched_end",
    "scheduled end": "sched_end",
    "sched hours": "sched_hours",
    "scheduled hours": "sched_hours",
    "actual start": "actual_start",
    "lunch out": "lunch_out",
    "lunch in": "lunch_in",
    "actual end": "actual_end",
    "hours": "hours_worked",
    "hours worked": "hours_worked",
    "absent": "absent",
    "yes": "sched_yes",       # schedule changed Yes column
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
    """Return {(row, col): text} for every cell in the table."""
    cells = {}
    for rel in table.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for cid in rel["Ids"]:
                cell = block_map.get(cid)
                if cell and cell["BlockType"] == "CELL":
                    r, c = cell["RowIndex"], cell["ColumnIndex"]
                    cells[(r, c)] = get_cell_text(cell, block_map)
    return cells


def build_col_map(cells: dict) -> dict:
    """
    Read row 1 as the header and return {col_index: field_name}.
    The second "no" column (schedule changed No) is mapped to "sched_no".
    """
    max_col = max(c for _, c in cells.keys()) if cells else 0
    col_map = {}
    seen_no = False

    for col in range(1, max_col + 1):
        header_text = cells.get((1, col), "").strip().lower()
        if not header_text:
            continue
        if header_text == "no":
            if seen_no:
                col_map[col] = "sched_no"
                continue
            seen_no = True
        field = HEADER_MAP.get(header_text)
        if field:
            col_map[col] = field

    return col_map


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
    """Extract key-value form fields (Project, Date, Weather, etc.) from a page."""
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


def parse_numeric(val: str):
    if not val:
        return None
    try:
        return float(val.replace(",", "."))
    except ValueError:
        return None


def parse_entries(
    cells: dict,
    col_map: dict,
    staff_type: str,
    source_file: str,
    textract_job_id: str,
    work_date,
    project: str,
    business_unit: str,
    day_of_week: str,
    weather: str,
) -> list:
    if not cells or not col_map:
        return []

    max_row = max(r for r, _ in cells.keys())
    has_sched_yes = "sched_yes" in col_map.values()
    entries = []

    for row_idx in range(2, max_row + 1):
        row = {col: cells.get((row_idx, col), "").strip() for col in col_map}

        # Resolve field values from dynamic col_map
        def field(name: str) -> str:
            for col, f in col_map.items():
                if f == name:
                    return row.get(col, "")
            return ""

        employee_name = field("employee_name")
        if not employee_name:
            continue  # skip blank/signature-only rows

        absent_raw = field("absent")
        absent = bool(absent_raw)  # any non-empty text = absent

        schedule_changed = False
        if has_sched_yes:
            schedule_changed = bool(field("sched_yes"))

        entries.append({
            "source_file": source_file,
            "textract_job_id": textract_job_id,
            "work_date": work_date,
            "project": project or None,
            "business_unit": business_unit or None,
            "day_of_week": day_of_week or None,
            "weather": weather or None,
            "staff_type": staff_type,
            "row_no": int(field("row_no")) if field("row_no").isdigit() else None,
            "job_task": field("job_task") or None,
            "title": field("title") or None,
            "employee_name": employee_name,
            "ein": field("ein") or None,
            "sched_start": field("sched_start") or None,
            "sched_end": field("sched_end") or None,
            "sched_hours": parse_numeric(field("sched_hours")),
            "actual_start": field("actual_start") or None,
            "lunch_out": field("lunch_out") or None,
            "lunch_in": field("lunch_in") or None,
            "actual_end": field("actual_end") or None,
            "hours_worked": parse_numeric(field("hours_worked")),
            "absent": absent,
            "schedule_changed": schedule_changed,
        })

    return entries


def lambda_handler(event: dict, context) -> dict:
    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])
        job_id = message["JobId"]
        job_status = message["Status"]

        if job_status != "SUCCEEDED":
            logger.warning("Textract job %s status: %s — skipping", job_id, job_status)
            continue

        s3_key = message.get("DocumentLocation", {}).get("S3ObjectName", "")
        source_file = s3_key.split("/")[-1] if s3_key else job_id

        try:
            blocks = get_all_blocks(job_id)
            block_map = {b["Id"]: b for b in blocks}
            tables = [b for b in blocks if b["BlockType"] == "TABLE"]

            conn = get_db_connection()
            try:
                total_entries = 0
                with conn:
                    with conn.cursor() as cur:
                        for table in tables:
                            page = table.get("Page", 1)
                            cells = get_table_cells(table, block_map)
                            col_map = build_col_map(cells)

                            if "employee_name" not in col_map.values():
                                continue  # not an employee roster table

                            staff_type = detect_staff_type(table, blocks)
                            header = extract_header(blocks, page)

                            project = header.get("project") or header.get("project name") or ""
                            business_unit = header.get("business unit") or header.get("bu") or ""
                            day_of_week = header.get("day of week") or header.get("day") or ""
                            weather = header.get("weather") or ""
                            work_date = parse_date(header.get("date", ""))

                            entries = parse_entries(
                                cells, col_map, staff_type,
                                source_file, job_id,
                                work_date, project, business_unit,
                                day_of_week, weather,
                            )

                            for e in entries:
                                cur.execute(
                                    """
                                    INSERT INTO timesheet_entries (
                                        source_file, textract_job_id, work_date,
                                        project, business_unit, day_of_week, weather,
                                        staff_type, row_no, job_task, title,
                                        employee_name, ein, sched_start, sched_end,
                                        sched_hours, actual_start, lunch_out, lunch_in,
                                        actual_end, hours_worked, absent, schedule_changed
                                    ) VALUES (
                                        %(source_file)s, %(textract_job_id)s, %(work_date)s,
                                        %(project)s, %(business_unit)s, %(day_of_week)s, %(weather)s,
                                        %(staff_type)s, %(row_no)s, %(job_task)s, %(title)s,
                                        %(employee_name)s, %(ein)s, %(sched_start)s, %(sched_end)s,
                                        %(sched_hours)s, %(actual_start)s, %(lunch_out)s, %(lunch_in)s,
                                        %(actual_end)s, %(hours_worked)s, %(absent)s, %(schedule_changed)s
                                    )
                                    """,
                                    e,
                                )
                                total_entries += 1

                logger.info("Wrote %d entries for job %s (%s)", total_entries, job_id, source_file)
            finally:
                conn.close()

        except Exception as e:
            logger.error("Error processing job %s: %s", job_id, e)
            raise

    return {"statusCode": 200}
