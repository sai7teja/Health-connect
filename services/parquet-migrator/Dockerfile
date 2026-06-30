FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=True
ENV APP_HOME=/app
WORKDIR $APP_HOME

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py migrate_health.py ./

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 main:app
