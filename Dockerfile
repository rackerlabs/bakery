FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir -r /build/requirements.txt

FROM node:20-alpine AS ui-builder

WORKDIR /build/ui

COPY ui/package.json ui/package-lock.json ./
RUN npm ci

COPY ui/ ./
RUN npm run build

FROM python:3.11-slim AS bakery-runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --chown=appuser:appuser bakery/ /app/bakery/
COPY --chown=appuser:appuser shared/ /app/shared/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "bakery.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM node:20-alpine AS bakery-ui-runtime

WORKDIR /app

ENV NODE_ENV=production \
    NPM_CONFIG_UPDATE_NOTIFIER=false

RUN npm install --global serve@14.2.4

COPY --from=ui-builder /build/ui/dist /app

USER node

EXPOSE 8080

CMD ["serve", "-s", "/app", "-l", "8080"]
