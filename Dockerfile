# syntax=docker/dockerfile:1
FROM python:3.13-slim

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m appuser && mkdir -p /app/instance && chown -R appuser:appuser /app
USER appuser

# default envs 
ENV PORT=5050
# persist DB inside
ENV DB_PATH=/app/instance/moviewatchlist.db
ENV FLASK_ENV=production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 5050

CMD ["python", "app.py"]
