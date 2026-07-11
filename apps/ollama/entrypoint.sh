#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-llama2:13b}"
MODELS_DIR="${OLLAMA_MODELS:-/data}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

mkdir -p "${MODELS_DIR}"
export OLLAMA_MODELS="${MODELS_DIR}"

echo "[CED-Llama] OLLAMA_HOST=${OLLAMA_HOST:-[::]:11434}"
echo "[CED-Llama] OLLAMA_MODELS=${OLLAMA_MODELS}"
echo "[CED-Llama] OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
echo "[CED-Llama] OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
echo "[CED-Llama] MODEL=${MODEL}"

ollama serve &
SERVE_PID=$!

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
  echo "[CED-Llama] Pulling ${MODEL}..."
  ollama pull "${MODEL}" || {
    echo "[CED-Llama] ERROR: pull failed for ${MODEL} — check disk/RAM"
    exit 1
  }
fi

echo "[CED-Llama] Warming text model ${MODEL}..."
if ollama run "${MODEL}" "ok" >/dev/null 2>&1; then
  echo "[CED-Llama] Text model warm"
else
  echo "[CED-Llama] WARN: text warm failed — first request may be slow"
fi

echo "[CED-Llama] Ready — listening on ${OLLAMA_HOST}"
wait "${SERVE_PID}"
