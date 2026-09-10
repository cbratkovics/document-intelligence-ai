# Runtime image for the Document Intelligence RAG System.
#
#   docker build -f docker/Dockerfile --target runtime -t doc-intel .
#   docker run --rm -p 8000:8000 -v doc-intel-data:/app/data doc-intel
#
# The runtime target installs the core requirements only (lexical retrieval,
# PDF/text ingestion, API). It has no provider keys and downloads no models.
# The optional "ml" target adds the OpenAI client and local-model libraries.

FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANONYMIZED_TELEMETRY=False \
    DATA_DIR=/app/data \
    HF_HOME=/app/models

COPY requirements-base.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-base.txt

COPY src/ /app/src/
COPY eval/ /app/eval/
COPY scripts/ /app/scripts/

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data /app/models \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python /app/scripts/health_check.py || exit 1
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS ml
USER root
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt
USER appuser
