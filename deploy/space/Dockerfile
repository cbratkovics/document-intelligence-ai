# Hugging Face Space image for the public retrieval demo.
#
# Assembled by .github/workflows/deploy-space.yml: this file sits at the root
# of the Space repository next to src/, app/, scripts/, data/samples/,
# requirements-*.txt, demo.env, and the Space README.
#
# Zero-cost configuration: no provider SDK is installed, GENERATION_PROVIDER
# is "none", and the ONNX embedding model is downloaded once at build time.
# The container runs as uid 1000, listens on 7860, and writes only under
# /home/user. API_KEY is supplied as a Space secret at runtime, never baked in.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ANONYMIZED_TELEMETRY=False \
    HF_HUB_DISABLE_TELEMETRY=1

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements-base.txt requirements-demo.txt ./
RUN pip install --upgrade pip && pip install -r requirements-demo.txt

COPY src/ ./src/
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/samples/ ./data/samples/
COPY demo.env ./demo.env
RUN mkdir -p /home/user/models/fastembed /home/user/data \
    && chown -R user:user /app /home/user

USER user
ENV HOME=/home/user \
    PYTHONPATH=/app \
    APP_ENV_FILE=/app/demo.env \
    FASTEMBED_CACHE_DIR=/home/user/models/fastembed

# Build-time model download (network is available while building). At runtime
# ALLOW_MODEL_DOWNLOAD=false in demo.env and HF_HUB_OFFLINE=1 keep it offline.
RUN python scripts/setup/init_models.py --fastembed --fastembed-cache-dir /home/user/models/fastembed
ENV HF_HUB_OFFLINE=1

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
