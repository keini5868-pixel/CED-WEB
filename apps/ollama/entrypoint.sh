#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-llama2:13b}"

echo "[CED-Llama] Starting Ollama on ${OLLAMA_HOST:-0.0.0.0:11434}"
ollama serve &
SERVE_PID=$!

# Esperar a que el daemon responda.
for i in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[CED-Llama] Pulling model ${MODEL} (first boot may take several minutes)..."
ollama pull "${MODEL}" || echo "[CED-Llama] WARN: pull failed — will retry on next restart"

wait "${SERVE_PID}"
