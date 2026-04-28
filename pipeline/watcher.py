"""
Local development trigger: watches the /input folder for new PDFs.

Run with:
    python watcher.py

Or via Docker Compose (default entrypoint for local dev).
"""
import logging
import os
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from db.migrations import run_migrations
from processor import process_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/input"))


class PDFHandler(FileSystemEventHandler):
    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".pdf":
            return
        log.info("New PDF detected: %s", path.name)
        try:
            doc_id = process_pdf(path)
            log.info("Processed successfully — doc_id=%d", doc_id)
        except Exception:
            log.exception("Error processing %s", path.name)


def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Running migrations …")
    run_migrations()

    log.info("Watching %s for new PDFs …", INPUT_DIR)
    handler = PDFHandler()
    observer = Observer()
    observer.schedule(handler, str(INPUT_DIR), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
