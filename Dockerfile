FROM python:3.13-slim

# Creating app user first so we can set ownership later
ARG APP_USER=appuser
RUN useradd -m -u 1000 -s /bin/bash ${APP_USER}

WORKDIR /app


RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Instaling Python 
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .

# Ensure instance/ exists and is writable by non-root user
RUN mkdir -p /app/instance && chown -R ${APP_USER}:${APP_USER} /app


USER ${APP_USER}

# Env
ENV FLASK_APP=app.py \
    PORT=5050
EXPOSE 5050


CMD ["python", "app.py"]
