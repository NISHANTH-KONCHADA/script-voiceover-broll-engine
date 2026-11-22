#!/bin/sh
set -e

# Start embedded MinIO (S3-compatible object storage for job artifacts)
minio server /data --address ":9000" --console-address ":9001" &
MINIO_PID=$!

# Wait for MinIO to become healthy
echo "Waiting for MinIO..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
        echo "MinIO is up."
        break
    fi
    sleep 1
done

# Start the API engine on the Spaces-required port
echo "Starting IncuBrix B-roll Engine on :${APP_PORT:-7860}..."
exec python -m broll_engine.main
