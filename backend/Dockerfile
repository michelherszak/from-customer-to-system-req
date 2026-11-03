FROM python:3.14.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ghostscript qpdf tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/kusys ./kusys
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY config ./config
COPY kusys-environment.yaml ./kusys-environment.yaml
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app \
    KUSYS_CONFIG_FILE=/app/config/kusys.example.yaml
CMD ["uvicorn", "kusys.main:app", "--host", "0.0.0.0", "--port", "8000"]
