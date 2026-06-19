# Castillo Digital API — producción (Railway / Render)
# build: 2026-06-19-single-voice-v12
FROM python:3.12-slim

ARG BUILD_VERSION=2026-06-19-single-voice-v12
LABEL org.ced.build="${BUILD_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN pip install -r requirements.txt

COPY apps/api/app ./app
COPY apps/api/data ./data

# Railway inyecta PORT (shell form — probado en producción)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
