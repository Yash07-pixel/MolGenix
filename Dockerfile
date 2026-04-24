FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libxrender1 \
    libxext6 \
    libx11-6 \
    openbabel \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG VINA_VERSION=1.2.5
ARG TARGETARCH
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) VINA_ARCH="x86_64" ;; \
      arm64) VINA_ARCH="aarch64" ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH:-unknown}"; exit 1 ;; \
    esac; \
    wget -O /usr/local/bin/vina "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v${VINA_VERSION}/vina_${VINA_VERSION}_linux_${VINA_ARCH}"; \
    chmod +x /usr/local/bin/vina; \
    /usr/local/bin/vina --help >/dev/null

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt
RUN mkdir -p /app/reports

COPY backend/ ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "/app/start.sh"]
