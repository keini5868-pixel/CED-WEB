#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-llama2:13b}"
MODELS_DIR="${OLLAMA_MODELS:-/data}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-6}"

mkdir -p "${MODELS_DIR}"
export OLLAMA_MODELS="${MODELS_DIR}"

echo "[CED-Llama] OLLAMA_HOST=${OLLAMA_HOST:-[::]:11434}"
echo "[CED-Llama] OLLAMA_MODELS=${OLLAMA_MODELS}"
echo "[CED-Llama] OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
echo "[CED-Llama] MODEL=${MODEL}"

ollama serve &
SERVE_PID=$!

# Esperar a que el daemon responda (hasta 2 min en cold start).
for i in $(seq 1 120); do
  if ollama list >/dev/null 2>&1; then
    echo "[CED-Llama] Ollama daemon ready (${i}s)"
    break
  fi
  sleep 1
done

if ! ollama list >/dev/null 2>&1; then
  echo "[CED-Llama] ERROR: Ollama daemon did not start in 120s"
  exit 1
fi

if ollama list 2>/dev/null | grep -qi "${MODEL%%:*}"; then
  echo "[CED-Llama] Model ${MODEL} already present — skipping pull"
else
  echo "[CED-Llama] Model missing (volume resize / cold start) — pulling ${MODEL}..."
  echo "[CED-Llama] Size ~7.4GB — may take several minutes on first boot"
  ollama pull "${MODEL}" || {
    echo "[CED-Llama] ERROR: pull failed — check disk/RAM; exiting for Railway restart"
    exit 1
  }
fi

echo "[CED-Llama] Ready — listening on ${OLLAMA_HOST}"
wait "${SERVE_PID}"
