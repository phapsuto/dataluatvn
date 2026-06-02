# ─── Stage: Build ─────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . /app

# ─── Environment ──────────────────────────────────────────
ENV API_PORT=2004
ENV DB_PATH=vietnamese_legal_documents.db
ENV CONTENT_DB_PATH=content_store.db
ENV PYTHONUNBUFFERED=1

# Expose API port
EXPOSE 2004

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:2004/ || exit 1

# Run API server
CMD ["python", "server.py"]
