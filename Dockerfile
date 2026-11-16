# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 AS uv

FROM python:3.12-slim AS builder

COPY --from=uv /uv /uvx /bin/

WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --extra web --extra postgres

FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 zcoder && \
    useradd --uid 1000 --gid zcoder --shell /bin/bash --create-home zcoder

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=zcoder:zcoder . .

ENV HOME=/home/zcoder \
    PATH=/opt/venv/bin:$PATH \
    ZCODER_LOG_FORMAT=json \
    ZCODER_LOG_LEVEL=INFO \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER zcoder

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -m zcoder.main --health-check || exit 1

ENTRYPOINT ["python", "scripts/docker_entrypoint.py", "python", "-m", "zcoder.main"]
CMD ["--help"]
