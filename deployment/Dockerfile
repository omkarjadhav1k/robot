# ==============================================================================
# Business AI Robot — Cloud Production Dockerfile
# ==============================================================================
FROM python:3.11-slim as base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies (including libpq for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy backend application code
COPY backend /app

# Expose port (default 8000 or Cloud Run $PORT)
EXPOSE 8000

# Run uvicorn server (Cloud Run injects PORT environment variable)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
