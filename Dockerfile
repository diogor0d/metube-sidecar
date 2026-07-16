FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

RUN groupadd --system sidecar \
    && useradd --system --gid sidecar --home-dir /nonexistent sidecar \
    && mkdir -p /data \
    && chown sidecar:sidecar /data

USER sidecar

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

