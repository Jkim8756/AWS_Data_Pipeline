"""
Claude Vision OCR client.

Uses claude-opus-4-7 with:
  - Prompt caching on the system prompt (stable across all pages)
  - Streaming to avoid request timeouts on large pages
  - Returns structured JSON extracted directly from the timesheet image
"""
import base64
import os
from pathlib import Path

import anthropic

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ---------------------------------------------------------------------------
# System prompt — cached once per process (cache_control: ephemeral)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert timesheet OCR assistant. You extract structured data
from employee timesheet images with perfect accuracy.

For each page you receive, return ONLY a valid JSON object with this exact shape:

{
  "employees": [
    {
      "name": "<full name>",
      "employee_id": "<id if present, else null>",
      "entries": [
        {
          "date": "<YYYY-MM-DD>",
          "day_of_week": "<Monday|Tuesday|...>",
          "time_in": "<HH:MM 24h or null>",
          "time_out": "<HH:MM 24h or null>",
          "break_minutes": <integer or null>,
          "hours_worked": <float or null>,
          "notes": "<any notes or null>"
        }
      ],
      "total_hours": <float or null>,
      "signature_present": <true|false>
    }
  ],
  "pay_period_start": "<YYYY-MM-DD or null>",
  "pay_period_end": "<YYYY-MM-DD or null>",
  "department": "<department name or null>",
  "notes": "<any page-level notes or null>"
}

Rules:
- Convert all times to 24-hour format (e.g. "2:30 PM" → "14:30").
- If a field is illegible or absent, use null — never guess.
- If a page has no timesheet data (e.g. cover page), return {"employees": []}.
- Return ONLY the JSON — no markdown fences, no explanation."""


def ocr_page(image_path: str | Path) -> dict:
    """
    Run Claude Vision on a single page image.

    Parameters
    ----------
    image_path : path to the PNG/JPEG page image

    Returns
    -------
    dict  — parsed JSON from Claude's response
    """
    image_path = Path(image_path)
    suffix = image_path.suffix.lower()
    media_type_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    media_type = media_type_map.get(suffix, "image/png")

    image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    client = _get_client()

    # Stream to avoid timeout on slow API responses
    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                # Cache the system prompt — it's identical for every page
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract all timesheet data from this page and return JSON.",
                    },
                ],
            }
        ],
    ) as stream:
        message = stream.get_final_message()

    raw_text = message.content[0].text.strip()

    # Strip accidental markdown fences if the model adds them
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    import json

    return json.loads(raw_text)
