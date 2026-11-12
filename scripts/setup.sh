#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

wait_for() {
    step=$1
    shift
    attempts=0
    until "$@" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 60 ]; then
            printf '%s\n' "$step did not become ready." >&2
            "$@" || true
            exit 1
        fi
        sleep 2
    done
}

docker info --format '{{.ServerVersion}}'
[ -e .env ] || cp .env.example .env
if [ -f security_events.jsonl ] && [ ! -e audit/security_events.jsonl ]; then
    mkdir -p audit
    cp security_events.jsonl audit/
fi
docker compose -f docker-compose.embedder.yml up -d embedder
docker compose -f docker-compose.llm.yml up -d llm
docker compose up -d --build
wait_for API docker compose exec -T api curl -fsS --max-time 5 http://127.0.0.1:8000/health

ensure_model() {
    service=$1
    setting=$2
    file="docker-compose.$service.yml"
    model=$(docker compose exec -T api python -c "from app.configs import settings; print(settings.$setting.model_name)")
    wait_for "Ollama ($service)" docker compose -f "$file" exec -T "$service" ollama list
    if ! docker compose -f "$file" exec -T "$service" ollama show "$model" >/dev/null 2>&1; then
        docker compose -f "$file" exec -T "$service" ollama pull "$model"
    fi
}

ensure_model embedder embedding
ensure_model llm llm
wait_for 'API connection to Ollama' docker compose exec -T api python -c '
import os
from urllib.parse import urljoin
from urllib.request import urlopen
for name in ("EMBEDDING_URL", "LLM_URL"):
    with urlopen(urljoin(os.environ[name], "/api/tags"), timeout=5):
        pass
'
docker compose exec -T api python -m scripts.seed_data
printf '%s\n' 'Ready. Swagger: http://localhost:8000/docs'
