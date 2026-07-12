# syntax=docker/dockerfile:1
# ── Build stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as a dedicated non-root user, not root.
RUN groupadd --gid 1000 zcoder && \
    useradd --uid 1000 --gid zcoder --shell /bin/bash --create-home zcoder

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=zcoder:zcoder . .

# Config/cache live under the app user's home, not in the image layer.
ENV HOME=/home/zcoder \
    ZCODER_LOG_FORMAT=json \
    ZCODER_LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER zcoder

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python main.py --health-check || exit 1

ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
