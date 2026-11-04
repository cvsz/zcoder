#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_DIR="/var/backups/wal_archive"
BASE_DIR="/var/backups/base_backups"
PASSWORD_FILE="${PGPASSWORD_FILE:-/run/secrets/zcoder_postgres_password}"

if [[ -f "$PASSWORD_FILE" ]]; then
    export PGPASSWORD
    PGPASSWORD="$(cat "$PASSWORD_FILE")"
fi

mkdir -p "$ARCHIVE_DIR" "$BASE_DIR"

echo "=========================================================="
echo "[zPITR] Starting zPITR Service for ${PGHOST}:${PGPORT}..."
echo "  Target Database: ${PGDATABASE:-zcoder_db}"
echo "  WAL Destination: ${ARCHIVE_DIR}"
echo "  Base Backup Dir: ${BASE_DIR}"
echo "=========================================================="

# ตรวจสอบการเข้าถึง Primary Database
until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER"; do
    echo "[zPITR] Waiting for PostgreSQL at ${PGHOST}:${PGPORT}..."
    sleep 2
done

echo "[zPITR] Primary PostgreSQL is ready."

# ตรวจสอบว่าโหมดคำสั่งเป็นอะไร (Default คือ continuous daemon)
CMD="${1:-daemon}"

if [[ "$CMD" == "drill" ]]; then
    echo "[zPITR] Executing on-demand restore drill..."
    exec /app/scripts/run_restore_drill.sh
elif [[ "$CMD" == "basebackup" ]]; then
    echo "[zPITR] Executing manual base backup..."
    exec /app/scripts/run_basebackup.sh
elif [[ "$CMD" == "daemon" ]]; then
    echo "[zPITR] Starting continuous WAL streaming via pg_receivewal..."
    exec pg_receivewal \
        -h "$PGHOST" \
        -p "$PGPORT" \
        -U "$PGUSER" \
        -D "$ARCHIVE_DIR" \
        --synchronous \
        --verbose
else
    exec "$@"
fi
