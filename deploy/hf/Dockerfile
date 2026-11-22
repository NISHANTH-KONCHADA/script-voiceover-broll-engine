# Hugging Face Spaces Dockerfile — IncuBrix B-roll Engine
# Runs FastAPI (port 7860) + embedded MinIO (port 9000) in one container.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    fonts-inter \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# MinIO server binary (S3-compatible storage for outputs)
RUN curl -fsSL https://dl.min.io/server/minio/release/linux-amd64/minio \
    -o /usr/local/bin/minio && chmod +x /usr/local/bin/minio

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]"

COPY . .

# Pre-download the faster-whisper model so the first audio job is not slow
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" || true

RUN mkdir -p /app/data /app/tmp /app/outputs /data

ENV PYTHONPATH=/app/src \
    APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=7860 \
    APP_DEBUG=false \
    DATABASE_URL=sqlite+aiosqlite:////app/data/jobs.db \
    S3_ENDPOINT_URL=http://localhost:9000 \
    S3_ACCESS_KEY_ID=minioadmin \
    S3_SECRET_ACCESS_KEY=minioadmin \
    S3_BUCKET_NAME=broll-engine-bucket \
    S3_SECURE=false \
    MINIO_ROOT_USER=minioadmin \
    MINIO_ROOT_PASSWORD=minioadmin

EXPOSE 7860

COPY deploy/hf/start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
