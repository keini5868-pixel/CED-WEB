#!/bin/sh
set -e

VOICE_MODEL="${OLLAMA_VOICE_MODEL:-llama3.2:3b}"
MODELS_DIR="${OLLAMA_MODELS:-/data}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

mkdir -p "${MODELS_DIR}"
export OLLAMA_MODELS="${MODELS_DIR}"

echo "[CED-Llama-Voice] OLLAMA_HOST=${OLLAMA_HOST:-[::]:11434}"
echo "[CED-Llama-Voice] OLLAMA_MODELS=${OLLAMA_MODELS}"
echo "[CED-Llama-Voice] OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
echo "[CED-Llama-Voice] OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
echo "[CED-Llama-Voice] VOICE_MODEL=${VOICE_MODEL}"

ollama serve &
SERVE_PID=$!

for i in $(seq 1 120); do
  if ollama list >/dev/null 2>&1; then
    echo "[CED-Llama-Voice] Ollama daemon ready (${i}s)"
    break
  fi
  sleep 1
done

if ! ollama list >/dev/null 2>&1; then
  echo "[CED-Llama-Voice] ERROR: Ollama daemon did not start in 120s"
  exit 1
fi

if ollama list 2>/dev/null | grep -qi "${VOICE_MODEL%%:*}"; then
  echo "[CED-Llama-Voice] Model ${VOICE_MODEL} already present — skipping pull"
else
  echo "[CED-Llama-Voice] Pulling ${VOICE_MODEL}..."
  ollama pull "${VOICE_MODEL}" || {
    echo "[CED-Llama-Voice] ERROR: pull failed — check disk/RAM"
    exit 1
  }
fi

echo "[CED-Llama-Voice] Warming voice model ${VOICE_MODEL}..."
if ollama run "${VOICE_MODEL}" "ok" >/dev/null 2>&1; then
  echo "[CED-Llama-Voice] Voice model warm"
else
  echo "[CED-Llama-Voice] WARN: voice warm failed — first request may be slow"
fi

echo "[CED-Llama-Voice] Ready — listening on ${OLLAMA_HOST}"
wait "${SERVE_PID}"
