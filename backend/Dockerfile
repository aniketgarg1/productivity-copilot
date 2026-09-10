FROM python:3.11-slim

# Fail fast, no .pyc clutter, unbuffered logs so docker logs are live.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl is used by the container healthcheck below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini pytest.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app

RUN chmod +x scripts/entrypoint.sh

# Run as an unprivileged user rather than root.
RUN useradd --create-home --uid 10001 copilot \
 && chown -R copilot:copilot /app
USER copilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["scripts/entrypoint.sh"]

# Gunicorn supervises uvicorn workers: a crashed worker is replaced instead of
# taking the whole container down, which a bare `uvicorn` cannot do.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
