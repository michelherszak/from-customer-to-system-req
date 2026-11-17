FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OTEL_SDK_DISABLED=true CREWAI_TELEMETRY_DISABLED=true CREWAI_TRACING_ENABLED=false
WORKDIR /app
COPY ops/crewai/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/kusys/analysis/contracts.py ./contracts.py
COPY backend/kusys/documents/preparation.py ./document_preparation.py
COPY ops/crewai/runtime.py ./runtime.py
USER 65534:65534
ENV HOME=/tmp CREWAI_STORAGE_DIR=/tmp/crewai
CMD ["python", "runtime.py"]
