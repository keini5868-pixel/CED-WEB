#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-llama2:13b}"
VOICE_MODEL="${OLLAMA_VOICE_MODEL:-llama3.2:3b}"
MODELS_DIR="${OLLAMA_MODELS:-/data}"
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-1}"

mkdir -p "${MODELS_DIR}"
export OLLAMA_MODELS="${MODELS_DIR}"

echo "[CED-Llama] OLLAMA_HOST=${OLLAMA_HOST:-[::]:11434}"
echo "[CED-Llama] OLLAMA_MODELS=${OLLAMA_MODELS}"
echo "[CED-Llama] OLLAMA_NUM_PARALLEL=${OLLAMA_NUM_PARALLEL}"
echo "[CED-Llama] OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS}"
echo "[CED-Llama] MODEL=${MODEL}"
echo "[CED-Llama] VOICE_MODEL=${VOICE_MODEL}"

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

ensure_model() {
  m="$1"
  label="$2"
  if ollama list 2>/dev/null | grep -qi "${m%%:*}"; then
    echo "[CED-Llama] Model ${m} (${label}) already present — skipping pull"
  else
    echo "[CED-Llama] Pulling ${m} (${label})..."
    ollama pull "${m}" || {
      echo "[CED-Llama] ERROR: pull failed for ${m} — check disk/RAM"
      exit 1
    }
  fi
}

ensure_model "${MODEL}" "text/reasoning"
ensure_model "${VOICE_MODEL}" "voice/conversational"

echo "[CED-Llama] Ready — listening on ${OLLAMA_HOST}"
wait "${SERVE_PID}"
