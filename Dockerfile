FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY . /app

# Install Python requirements
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    requests \
    beautifulsoup4 \
    pyarrow \
    huggingface_hub

# Expose API port
EXPOSE 8080

# Run API server
CMD ["python", "server.py"]
