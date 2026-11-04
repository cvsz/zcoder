#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/var/backups/base_backups"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET_DIR="${BASE_DIR}/base_${TIMESTAMP}"

echo "[zPITR] Initiating physical base backup into: ${TARGET_DIR}..."

pg_basebackup \
    -h "$PGHOST" \
    -p "$PGPORT" \
    -U "$PGUSER" \
    -D "$TARGET_DIR" \
    -Ft \
    -z \
    -Xs \
    -P

# คำนวณ SHA-256 สำหรับไฟล์ Base Backup
sha256sum "${TARGET_DIR}/base.tar.gz" > "${TARGET_DIR}/base.tar.gz.sha256"
echo "[zPITR] Base backup completed successfully. Checksum:"
cat "${TARGET_DIR}/base.tar.gz.sha256"
