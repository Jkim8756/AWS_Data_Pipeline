"""
Core pipeline: PDF → page images → OCR → PostgreSQL.

Entry point for both the local watcher and the SQS worker.
"""
import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

import psycopg2.extras
from pdf2image import convert_from_path

from db.connection import get_conn
from ocr import claude_ocr, surya_ocr

log = logging.getLogger(__name__)

OCR_MODEL = os.environ.get("OCR_MODEL", "claude")  # "claude" | "surya"
DPI = int(os.environ.get("PDF_DPI", "200"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _upsert_document(conn, file_name: str, file_hash: str, **kwargs) -> int:
    """Insert or return existing document row; return its id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (file_name, file_hash, s3_bucket, s3_key)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE
                SET file_name  = EXCLUDED.file_name,
                    updated_at = NOW()
            RETURNING id
            """,
            (
                file_name,
                file_hash,
                kwargs.get("s3_bucket"),
                kwargs.get("s3_key"),
            ),
        )
        return cur.fetchone()[0]


def _set_status(conn, doc_id: int, status: str, error_msg: str | None = None):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET status=%s, error_msg=%s WHERE id=%s",
            (status, error_msg, doc_id),
        )


def _set_page_count(conn, doc_id: int, page_count: int):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET page_count=%s WHERE id=%s",
            (page_count, doc_id),
        )


# ---------------------------------------------------------------------------
# Per-page OCR
# ---------------------------------------------------------------------------

def _run_ocr(image_path: Path) -> tuple[dict | None, str | None]:
    """
    Returns (structured_data, extracted_text).
    structured_data is None when using the Surya fallback.
    """
    if OCR_MODEL == "surya" or (OCR_MODEL == "claude" and not os.environ.get("ANTHROPIC_API_KEY")):
        log.warning("Using Surya fallback (no ANTHROPIC_API_KEY set or OCR_MODEL=surya)")
        text = surya_ocr.ocr_page(image_path)
        word_count = len(text.split())
        return None, text

    result = claude_ocr.ocr_page(image_path)
    # Flatten employees text for word_count / full-text search
    texts = []
    for emp in result.get("employees", []):
        texts.append(emp.get("name", ""))
        for entry in emp.get("entries", []):
            if entry.get("notes"):
                texts.append(entry["notes"])
    extracted_text = " ".join(t for t in texts if t)
    return result, extracted_text


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: str | Path,
    *,
    s3_bucket: str | None = None,
    s3_key: str | None = None,
) -> int:
    """
    Process a single PDF.

    Parameters
    ----------
    pdf_path  : local path to the PDF file
    s3_bucket : originating S3 bucket (optional, stored for reference)
    s3_key    : originating S3 key    (optional, stored for reference)

    Returns
    -------
    int — document id
    """
    pdf_path = Path(pdf_path)
    file_name = pdf_path.name
    file_hash = _sha256(pdf_path)

    log.info("Processing %s  (hash=%s)", file_name, file_hash[:12])

    conn = get_conn()
    try:
        with conn:
            doc_id = _upsert_document(
                conn,
                file_name=file_name,
                file_hash=file_hash,
                s3_bucket=s3_bucket,
                s3_key=s3_key,
            )
            _set_status(conn, doc_id, "processing")

        with tempfile.TemporaryDirectory() as tmpdir:
            images = convert_from_path(str(pdf_path), dpi=DPI, output_folder=tmpdir)
            page_count = len(images)
            log.info("  %d page(s) detected", page_count)

            with conn:
                _set_page_count(conn, doc_id, page_count)

            rows = []
            for page_num, image in enumerate(images, start=1):
                img_path = Path(tmpdir) / f"page_{page_num:04d}.png"
                image.save(str(img_path), "PNG")

                log.info("  OCR page %d/%d …", page_num, page_count)
                structured_data, extracted_text = _run_ocr(img_path)

                word_count = len(extracted_text.split()) if extracted_text else 0
                rows.append(
                    (
                        doc_id,
                        page_num,
                        extracted_text,
                        json.dumps(structured_data) if structured_data else None,
                        word_count,
                    )
                )

            with conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_values(
                        cur,
                        """
                        INSERT INTO document_pages
                            (document_id, page_number, extracted_text, structured_data, word_count)
                        VALUES %s
                        ON CONFLICT (document_id, page_number) DO UPDATE SET
                            extracted_text  = EXCLUDED.extracted_text,
                            structured_data = EXCLUDED.structured_data,
                            word_count      = EXCLUDED.word_count
                        """,
                        rows,
                        template="(%s, %s, %s, %s::jsonb, %s)",
                    )
                _set_status(conn, doc_id, "done")

        log.info("  Done — doc_id=%d", doc_id)
        return doc_id

    except Exception as exc:
        log.exception("Failed to process %s", file_name)
        try:
            with conn:
                _set_status(conn, doc_id, "error", str(exc))
        except Exception:
            pass
        raise
    finally:
        conn.close()
