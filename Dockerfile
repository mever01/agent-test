FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app/ /app/app/
COPY data/ /app/data/
COPY scripts/ /app/scripts/
COPY tests/ /app/tests/
COPY alembic/ /app/alembic/
COPY alembic.ini .

RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
