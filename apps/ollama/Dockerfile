# CED-Llama — servicio Ollama en Railway (cerebro local)
FROM ollama/ollama:latest

ENV OLLAMA_HOST=0.0.0.0:11434

COPY apps/ollama/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 11434

ENTRYPOINT ["/entrypoint.sh"]
