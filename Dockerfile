FROM python:3.11-slim

# System dependencies: ffmpeg for media, curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    fonts-inter \
    fonts-indic \
    fonts-noto-core \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./

# Copy source code before installing the package
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]"

# Copy remaining project files
COPY . .

# Copy application source
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY openapi.yaml .
COPY .env.example .

# Create volume directories
RUN mkdir -p /app/data /app/tmp /app/outputs

ENV PYTHONPATH=/app/src
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "broll_engine.main"]
