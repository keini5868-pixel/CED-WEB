#!/bin/sh
set -e
PORT="${PORT:-8000}"
echo "[ced-api] starting uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
