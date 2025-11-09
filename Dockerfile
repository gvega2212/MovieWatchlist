# ==============================
# MovieWatchlist - Dockerfile
# ==============================
FROM python:3.13-slim AS base

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Copy dependency definitions first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Environment defaults
ENV FLASK_APP=app.py
ENV PORT=5050
EXPOSE 5050

# Create a non-root user for security
RUN useradd -m appuser
USER appuser

# Run the app
CMD ["python", "app.py"]
