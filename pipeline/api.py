"""
Optional FastAPI upload endpoint.

Provides a simple HTTP API for uploading PDFs when S3/SQS is not available
(e.g. local dev, Option B deployment on a VPS).

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000

Or start via Docker Compose with: ENTRYPOINT=api
"""
import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from db.migrations import run_migrations
from processor import process_pdf

log = logging.getLogger(__name__)

app = FastAPI(title="Timesheet OCR API", version="1.0")


@app.on_event("startup")
async def startup():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    log.info("Running migrations …")
    run_migrations()


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF and process it synchronously.

    Returns the document id and a summary of pages processed.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / file.filename
        contents = await file.read()
        local_path.write_bytes(contents)

        try:
            doc_id = process_pdf(local_path)
        except Exception as exc:
            log.exception("Processing failed for %s", file.filename)
            raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse({"doc_id": doc_id, "file_name": file.filename, "status": "done"})


@app.get("/health")
def health():
    return {"status": "ok"}
