# Organism single-device image — CPU only (no CUDA base).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORGANISM_PREFER_GPU=0 \
    ORGANISM_BIO_GPU_TWIN=0 \
    ORGANISM_NEURO_SIM=0 \
    ORGANISM_WETLAB_GPIO=0 \
    ORGANISM_LLM_ENABLED=0 \
    ORGANISM_SANDBOX_ISOLATE=1 \
    ORGANISM_GENERATIVE_BACKEND=template \
    ORGANISM_HEALTH_HOST=0.0.0.0 \
    ORGANISM_HEALTH_PORT=8787 \
    ORGANISM_CONFIG=/etc/organism/cpu_only.yaml

WORKDIR /opt/organism

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY sdk ./sdk
COPY modules ./modules
COPY proto ./proto
COPY deploy ./deploy
COPY harness ./harness

RUN python -m pip install --no-cache-dir -e ".[dev]" \
 && mkdir -p /var/lib/organism/artifacts /var/lib/organism/organisms \
 && true \
 && mkdir -p /etc/organism \
 && cp deploy/config/cpu_only.yaml /etc/organism/cpu_only.yaml

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health')" || exit 1

ENTRYPOINT ["python", "-m", "organism_sdk", "serve", "--config", "/etc/organism/cpu_only.yaml"]
