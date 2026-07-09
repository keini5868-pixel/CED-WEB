# CED-Llama — servicio Ollama en Railway (cerebro local)
FROM ollama/ollama:latest

# Railway private networking usa IPv6 — [::] acepta IPv4+IPv6 en Linux.
ENV OLLAMA_HOST=[::]:11434
# Montar volumen Railway en /data para persistir modelos (~7.4 GB).
ENV OLLAMA_MODELS=/data

COPY apps/ollama/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 11434

ENTRYPOINT ["/entrypoint.sh"]