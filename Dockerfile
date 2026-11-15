FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HT_DB_PATH=/data/records.db

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data

COPY backend/requirements.txt backend/requirements.txt
COPY requirements-prod.txt requirements-prod.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r requirements-prod.txt

COPY . .
RUN chown -R appuser:appuser /app

USER appuser
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health', timeout=3)"

CMD ["sh", "-c", "gunicorn --chdir backend --workers 1 --threads 4 --bind 0.0.0.0:${PORT:-8000} app:app"]
