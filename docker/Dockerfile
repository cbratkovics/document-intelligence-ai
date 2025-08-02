# Multi-stage Dockerfile for Document Intelligence AI
# Optimized to reduce image size and ensure no layer exceeds 500MB

# Stage 1: Runtime base (API-only mode)
FROM python:3.11-slim as runtime-base

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install base requirements
COPY requirements-base.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-base.txt && \
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

# Stage 2: ML Runtime (includes ML dependencies)
FROM runtime-base as runtime-ml

USER root

# Install build dependencies temporarily
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install ML requirements in one layer
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt && \
    rm -rf /root/.cache/pip && \
    find /usr/local -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /usr/local -type f -name "*.pyc" -delete 2>/dev/null || true

# Clean up build dependencies
RUN apt-get purge -y --auto-remove build-essential gcc g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER appuser

# Stage 3: Development image
FROM runtime-ml as development

USER root

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    git \
    vim \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dev requirements
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt && \
    rm -rf /root/.cache/pip

USER appuser