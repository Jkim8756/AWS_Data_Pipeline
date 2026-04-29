"""
Surya OCR fallback — free, self-hosted, no API key required.

Returns raw extracted text only (no structured JSON).
Install: pip install surya-ocr

Usage is gated behind SURYA_ENABLED=true so the container doesn't load
the model unless explicitly opted in (it pulls ~2 GB of weights).
"""
import os
from pathlib import Path


def is_available() -> bool:
    return os.environ.get("SURYA_ENABLED", "false").lower() == "true"


def ocr_page(image_path: str | Path) -> str:
    """
    Run Surya OCR on a single page image.

    Parameters
    ----------
    image_path : path to the PNG/JPEG page image

    Returns
    -------
    str — plain extracted text (lines joined with newlines)
    """
    if not is_available():
        raise RuntimeError(
            "Surya OCR is not enabled. Set SURYA_ENABLED=true and ensure "
            "surya-ocr is installed."
        )

    from PIL import Image
    from surya.ocr import run_ocr
    from surya.model.detection.model import load_model as load_det_model
    from surya.model.detection.processor import load_processor as load_det_processor
    from surya.model.recognition.model import load_model as load_rec_model
    from surya.model.recognition.processor import load_processor as load_rec_processor

    image = Image.open(image_path).convert("RGB")

    det_processor, det_model = load_det_processor(), load_det_model()
    rec_model, rec_processor = load_rec_model(), load_rec_processor()

    langs = [os.environ.get("SURYA_LANG", "en")]
    results = run_ocr(
        [image], [langs], det_model, det_processor, rec_model, rec_processor
    )

    lines = []
    for text_line in results[0].text_lines:
        lines.append(text_line.text)

    return "\n".join(lines)
