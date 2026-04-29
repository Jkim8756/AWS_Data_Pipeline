FROM python:3.13-slim

# poppler-utils: required by pdf2image for PDF → PNG conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: local watcher mode
# Override in docker-compose or ECS task definition:
#   CMD ["python", "sqs_worker.py"]   ← production
#   CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]  ← API mode
CMD ["python", "watcher.py"]
