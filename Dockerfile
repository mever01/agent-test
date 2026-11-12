FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY app/ /app/app/
COPY core/ /app/core/
COPY data/ /app/data/
COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
COPY alembic/ /app/alembic/
COPY alembic.ini .

RUN uv sync --locked --no-cache

ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
