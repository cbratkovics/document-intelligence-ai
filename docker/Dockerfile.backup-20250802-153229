# Multi-stage Dockerfile for Document Intelligence AI
# Optimized to reduce image size from 3.31GB to under 1GB

# Stage 1: Build wheels
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-base.txt .

# Build wheels for base dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements-base.txt

# Stage 2: Runtime base (API-only mode)
FROM python:3.11-slim as runtime-base

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels and install base dependencies
COPY --from=builder /build/wheels /wheels
COPY requirements-base.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-base.txt && \
    rm -rf /wheels && \
    rm -rf /root/.cache/pip

# Copy application code
COPY src/ /app/src/
COPY scripts/ /app/scripts/

# Create directories
RUN mkdir -p /app/data /app/logs /app/models

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV MODEL_CACHE_DIR=/app/models

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: ML Runtime (includes ML dependencies)
FROM runtime-base as runtime-ml

USER root

# Install build tools temporarily for ML packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy ML requirements
COPY requirements-ml.txt .

# Install ML dependencies separately to keep layers small
RUN pip install --no-cache-dir langchain==0.2.16 && \
    pip install --no-cache-dir langchain-community==0.2.16 && \
    pip install --no-cache-dir langchain-openai==0.1.25 && \
    pip install --no-cache-dir chromadb==0.4.22 && \
    pip install --no-cache-dir pandas==2.0.3 && \
    pip install --no-cache-dir celery==5.3.4 && \
    pip install --no-cache-dir rank-bm25==0.2.2

# Note: sentence-transformers is NOT installed here to keep image under 1GB
# It will be downloaded on first use via the init_models.py script
# If you need it pre-installed, uncomment the following:
# RUN pip install --no-cache-dir --no-deps sentence-transformers==2.2.2 && \
#     rm -rf /root/.cache/pip

# Clean up build dependencies
RUN apt-get purge -y --auto-remove build-essential gcc g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    find /usr/local -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

USER appuser

# Stage 4: Development image
FROM runtime-ml as development

USER root

# Reinstall build tools for development
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Copy dev requirements and install
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt && \
    rm -rf /root/.cache/pip

USER appuser