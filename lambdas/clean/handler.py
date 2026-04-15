"""
Lambda: clean
Trigger : SNS pdf-textract-completion (Textract async callback)
Action  : Fetch Textract results, parse timesheet tables, compute
          confidence, write raw JSON to S3, then route:
            - high confidence → SQS write queue (or direct DB write)
            - low  confidence → SQS review queue
"""
import json
import os
import re
import boto3
import sys
sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

from dotenv import load_dotenv
load_dotenv()

textract_client = boto3.client("textract", region_name="us-east-2")
sqs_client      = boto3.client("sqs",      region_name="us-east-2")
s3_client       = boto3.client("s3")

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", 1.0))

# ── Column name normalisation map ──────────────────────────────────────────────
_COL_MAP = {
    "employee name": "employee_name",
    "ein":           "ein",
    "scheduled start": "sched_start",
    "sched start":   "sched_start",
    "scheduled end": "sched_end",
    "sched end":     "sched_end",
    "scheduled hours": "sched_hours",
    "sched hours":   "sched_hours",
    "actual start":  "actual_start",
    "lunch out":     "lunch_out",
    "lunch in":      "lunch_in",
    "actual end":    "actual_end",
    "hours":         "actual_hours",
    "actual hours":  "actual_hours",
    "absent":        "absent",
    "no":            "schedule_changed_no",   # "Changes from scheduled — No"
    "yes":           "schedule_changed_yes",  # "Changes from scheduled — Yes"
    "title":         "title",
    "job task":      "job_task",
}


def _normalise_col(raw: str) -> str:
    return _COL_MAP.get(raw.lower().strip(), raw.lower().strip().replace(" ", "_"))


def _fetch_all_blocks(job_id: str) -> list[dict]:
    """Paginate through all Textract blocks for a job."""
    blocks, next_token = [], None
    while True:
        kwargs = {"JobId": job_id}
        if next_token:
            kwargs["NextToken"] = next_token
        resp = textract_client.get_document_analysis(**kwargs)
        blocks.extend(resp.get("Blocks", []))
        next_token = resp.get("NextToken")
        if not next_token:
            break
    return blocks


def _blocks_to_table(blocks: list[dict]) -> list[list[str]]:
    """
    Extract the first TABLE found in Textract blocks as a 2-D list of strings.
    Returns rows × columns.
    """
    block_map    = {b["Id"]: b for b in blocks}
    table_blocks = [b for b in blocks if b["BlockType"] == "TABLE"]
    if not table_blocks:
        return []

    table = table_blocks[0]
    cells: dict[tuple[int, int], str] = {}

    for rel in table.get("Relationships", []):
        if rel["Type"] != "CHILD":
            continue
        for cell_id in rel["Ids"]:
            cell = block_map.get(cell_id, {})
            if cell.get("BlockType") != "CELL":
                continue
            r, c = cell["RowIndex"], cell["ColumnIndex"]
            words = []
            for wrel in cell.get("Relationships", []):
                if wrel["Type"] == "CHILD":
                    for wid in wrel["Ids"]:
                        w = block_map.get(wid, {})
                        if w.get("BlockType") == "WORD":
                            words.append(w.get("Text", ""))
            cells[(r, c)] = " ".join(words)

    if not cells:
        return []

    max_r = max(r for r, _ in cells)
    max_c = max(c for _, c in cells)
    return [
        [cells.get((r, c), "") for c in range(1, max_c + 1)]
        for r in range(1, max_r + 1)
    ]


def _avg_confidence(blocks: list[dict]) -> float:
    """Mean confidence of all WORD blocks, clamped 0-1."""
    scores = [
        b["Confidence"] / 100.0
        for b in blocks
        if b["BlockType"] == "WORD" and "Confidence" in b
    ]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _parse_header_block(blocks: list[dict]) -> dict:
    """
    Extract project-level fields from LINE blocks at the top of the page.
    Returns dict with date, day, business_unit, project.
    """
    lines = [
        b.get("Text", "")
        for b in blocks
        if b["BlockType"] == "LINE"
    ]
    header: dict[str, str] = {}
    for line in lines:
        lw = line.lower()
        if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", line) and "date" not in header:
            m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", line)
            if m:
                header["date"] = m.group(1)
        if "monday" in lw:   header["day"] = "Monday"
        if "tuesday" in lw:  header["day"] = "Tuesday"
        if "wednesday" in lw: header["day"] = "Wednesday"
        if "thursday" in lw: header["day"] = "Thursday"
        if "friday" in lw:   header["day"] = "Friday"
        if "saturday" in lw: header["day"] = "Saturday"
        if "sunday" in lw:   header["day"] = "Sunday"
        if re.search(r"\d{5,}", line) and "business_unit" not in header:
            m = re.search(r"(\d+\.?\d*)", line)
            if m:
                header["business_unit"] = m.group(1)
        if "ceiling" in lw or "construction" in lw or "clean" in lw:
            header["project"] = line.strip()
    return header


def _table_to_records(
    rows: list[list[str]],
    header: dict,
    source_file: str,
    page: int,
    confidence: float,
    job_id: str,
    staff_type: str = "Frontline",
) -> list[dict]:
    """
    Convert a 2-D table into a list of record dicts matching the xlsx schema.
    Skips rows without an employee name.
    """
    if len(rows) < 2:
        return []

    # Find column headers row (first row containing "Employee" or "EIN")
    header_row_idx = 0
    for i, row in enumerate(rows):
        joined = " ".join(row).lower()
        if "employee" in joined or "ein" in joined:
            header_row_idx = i
            break

    col_headers = [_normalise_col(c) for c in rows[header_row_idx]]
    records = []

    for row in rows[header_row_idx + 1:]:
        if len(row) < len(col_headers):
            row = row + [""] * (len(col_headers) - len(row))
        cell = dict(zip(col_headers, row))

        name = cell.get("employee_name", "").strip()
        if not name or name.lower() in ("employee name", ""):
            continue

        absent_val = cell.get("absent", "").strip()

        rec = {
            "source_file":      source_file,
            "page":             page,
            "date":             header.get("date"),
            "day":              header.get("day"),
            "business_unit":    header.get("business_unit"),
            "project":          header.get("project"),
            "staff_type":       staff_type,
            "job_task":         cell.get("job_task", ""),
            "title":            cell.get("title", ""),
            "employee_name":    name,
            "ein":              cell.get("ein", ""),
            "sched_start":      cell.get("sched_start", ""),
            "sched_end":        cell.get("sched_end", ""),
            "sched_hours":      cell.get("sched_hours", ""),
            "actual_start":     cell.get("actual_start", ""),
            "lunch_out":        cell.get("lunch_out", ""),
            "lunch_in":         cell.get("lunch_in", ""),
            "actual_end":       cell.get("actual_end", ""),
            "actual_hours":     cell.get("actual_hours", ""),
            "absent":           absent_val if absent_val else None,
            "schedule_changed": cell.get("schedule_changed_yes", ""),
            "confidence":       confidence,
            "status":           "auto_accepted" if confidence >= CONFIDENCE_THRESHOLD else "needs_review",
            "textract_job_id":  job_id,
        }
        records.append(rec)

    return records


def _save_raw_json(records: list[dict], job_id: str, source_file: str) -> str:
    """Write raw parsed records to S3; return the S3 key."""
    bucket = os.environ["S3_RAW_JSON_BUCKET"]
    safe_name = source_file.replace("/", "_").replace(" ", "_")
    key = f"raw/{job_id}/{safe_name}.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(records, default=str),
        ContentType="application/json",
    )
    print(f"[clean] Saved raw JSON → s3://{bucket}/{key}")
    return key


def handler(event: dict, context) -> dict:
    write_queue_url  = os.environ["SQS_WRITE_QUEUE_URL"]
    review_queue_url = os.environ["SQS_REVIEW_QUEUE_URL"]

    for sns_record in event.get("Records", []):
        message   = json.loads(sns_record["Sns"]["Message"])
        job_id    = message.get("JobId")
        job_status = message.get("Status")

        print(f"[clean] Textract JobId={job_id} Status={job_status}")

        if job_status != "SUCCEEDED":
            print(f"[clean] Job did not succeed — skipping")
            continue

        try:
            blocks     = _fetch_all_blocks(job_id)
            confidence = _avg_confidence(blocks)
            header     = _parse_header_block(blocks)
            rows       = _blocks_to_table(blocks)

            # Derive source_file from JobTag if available
            job_tag     = message.get("JobTag", "")
            source_file = job_tag if job_tag else "unknown.pdf"

            records = _table_to_records(
                rows, header,
                source_file=source_file,
                page=1,
                confidence=confidence,
                job_id=job_id,
            )

            print(f"[clean] Parsed {len(records)} records, confidence={confidence}")

            raw_json_key = _save_raw_json(records, job_id, source_file)

            payload = {
                "job_id":        job_id,
                "source_file":   source_file,
                "raw_json_key":  raw_json_key,
                "confidence":    confidence,
                "records":       records,
            }

            target_queue = (
                write_queue_url
                if confidence >= CONFIDENCE_THRESHOLD
                else review_queue_url
            )
            label = "write" if confidence >= CONFIDENCE_THRESHOLD else "review"

            sqs_client.send_message(
                QueueUrl    = target_queue,
                MessageBody = json.dumps(payload, default=str),
            )
            print(f"[clean] Routed to {label} queue")

        except Exception as exc:
            print(f"[clean] ERROR processing job {job_id}: {exc}")
            raise

    return {"statusCode": 200, "body": "OK"}