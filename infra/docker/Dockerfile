FROM python:3.10-slim

WORKDIR /app

# Build arguments
ARG ENV=dev
ARG MODEL_VERSION=latest

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Ensure proper env passes for configs
ENV PYTHONPATH=/app
ENV PORT=8080
ENV ENV=${ENV}
ENV MODEL_VERSION=${MODEL_VERSION}

EXPOSE 8080

# Health check for Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["gunicorn", "src.api.predict:app", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080", "--timeout", "120"]
