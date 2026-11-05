FROM alpine:3.20

# ติดตั้ง PostgreSQL 16 client, runtime utilities และ Python 3 สำหรับ evidence emitter
RUN apk add --no-cache \
    postgresql16-client \
    bash \
    curl \
    jq \
    coreutils \
    gzip \
    python3 \
    py3-pip

WORKDIR /app

# จัดเตรียมโครงสร้างไดเรกทอรีจัดเก็บ
RUN mkdir -p /var/backups/wal_archive \
             /var/backups/base_backups \
             /app/evidence \
             /app/scripts \
             /app/config

COPY entrypoint.sh /app/entrypoint.sh
COPY scripts/ /app/scripts/
COPY config/ /app/config/

RUN chmod +x /app/entrypoint.sh /app/scripts/*.sh /app/scripts/*.py

VOLUME ["/var/backups/wal_archive", "/var/backups/base_backups", "/app/evidence"]

ENTRYPOINT ["/app/entrypoint.sh"]
