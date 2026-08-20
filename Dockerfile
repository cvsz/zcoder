# syntax=docker/dockerfile:1
FROM python:3.14-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.14-slim AS runtime

RUN groupadd --gid 1000 zcoder && \
    useradd --uid 1000 --gid zcoder --shell /bin/bash --create-home zcoder

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=zcoder:zcoder . .

ENV HOME=/home/zcoder \
    ZCODER_LOG_FORMAT=json \
    ZCODER_LOG_LEVEL=INFO \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER zcoder

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -m zcoder.main --health-check || exit 1

ENTRYPOINT ["python", "-m", "zcoder.main"]
CMD ["--help"]
