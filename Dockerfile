# syntax=docker/dockerfile:1

FROM python:3.13-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m appuser && mkdir -p /app/instance && chown -R appuser:appuser /app
USER appuser

# Azure always passes PORT environment variable
# Flask must use PORT, not a hardcoded 5050
ENV PORT=8000
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_ENV=production

EXPOSE 8000

# Use gunicorn for Azure
CMD bash -c "gunicorn -w 4 -b 0.0.0.0:${PORT} app:app"
