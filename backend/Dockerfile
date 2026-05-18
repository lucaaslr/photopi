# PhotoPi backend image.
# python:3.11-slim has official linux/arm64 builds, so this Dockerfile runs
# unchanged on a Raspberry Pi 3B+ (aarch64) and on an x86 dev machine.
FROM python:3.11-slim

# --- System dependencies ---------------------------------------------------
# ffmpeg            -> video probing + thumbnail frame extraction
# libimage-exiftool -> metadata fallback for formats Pillow can't read
# The list is deliberately short to keep the image small on a Pi's SD card.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libimage-exiftool-perl \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# Non-root runtime user.
RUN useradd --create-home --uid 1000 photopi \
    && mkdir -p /data \
    && chown -R photopi:photopi /app /data
USER photopi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Single Uvicorn worker: one process keeps RAM flat on a 1GB Pi. The async
# event loop still handles many concurrent requests.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
