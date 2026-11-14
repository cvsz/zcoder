
#!/usr/bin/env bash
set -Eeuo pipefail

cd "$HOME/zcoder"

COMPOSE=(-f docker-compose.zpitr.yml)
CONTAINER="zPITR"
BACKUP_DIR="/var/backups/base_backups"

log() {
  printf '\n[%s] %s\n' "$(date -u +%FT%TZ)" "$*"
}

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

exec 9>/tmp/zcoder-pitr-basebackup.lock
flock -n 9 || fail "Another backup operation is running."

log "Checking zPITR container"
docker inspect "$CONTAINER" >/dev/null 2>&1 ||
  fail "zPITR container not found"

docker inspect "$CONTAINER" \
  --format '{{.State.Running}}' | grep -qx true ||
  fail "zPITR is not running"

log "Checking PostgreSQL availability"
docker compose exec -T zpostgressql \
  pg_isready -U zcoder -d zcoder_db ||
  fail "PostgreSQL is unavailable"

log "Checking source database size"
docker compose exec -T zpostgressql \
  psql -X -U zcoder -d zcoder_db -c \
  "SELECT current_database(),
          pg_size_pretty(pg_database_size(current_database()))
     AS database_size;"

log "Checking WAL streaming"
docker compose exec -T zpostgressql \
  psql -X -U zcoder -d zcoder_db -c "
    SELECT pid, application_name, state,
           sent_lsn, write_lsn, flush_lsn
      FROM pg_stat_replication
     WHERE application_name = 'pg_receivewal';
  "

log "Executing fresh base backup"
docker compose "${COMPOSE[@]}" exec -T zpitr \
  /app/scripts/run_basebackup.sh

log "Verifying backup artifacts"
docker compose "${COMPOSE[@]}" exec -T zpitr sh -lc '
  set -eu

  DIR="/var/backups/base_backups"

  LATEST="$(find "$DIR" -mindepth 1 -maxdepth 1 \
    -type d -name "base_*" | sort | tail -n 1)"

  test -n "$LATEST" || {
    echo "No base backup directory found"
    exit 1
  }

  echo "Backup directory: $LATEST"

  test -s "$LATEST/base.tar.gz" || {
    echo "Missing or empty base.tar.gz"
    exit 1
  }

  test -s "$LATEST/base.tar.gz.sha256" || {
    echo "Missing checksum"
    exit 1
  }

  cd "$LATEST"
  sha256sum -c base.tar.gz.sha256

  gzip -t base.tar.gz
  echo "Base archive gzip integrity: OK"

  echo "Archive contents:"
  tar -tzf base.tar.gz | head -40

  if [ -s pg_wal.tar.gz ]; then
    gzip -t pg_wal.tar.gz
    echo "WAL archive gzip integrity: OK"
  else
    echo "WARNING: No pg_wal.tar.gz found."
    echo "Inspect backup contents before attempting recovery."
  fi

  echo "Backup artifacts:"
  ls -lh "$LATEST"

  echo "Backup verification completed."
'

log "Checking WAL archive after backup"
docker compose "${COMPOSE[@]}" exec -T zpitr sh -lc '
  find /var/backups/wal_archive -maxdepth 1 -type f \
    -printf "%f %s bytes\n" | sort | tail -20

  echo "WAL archive disk usage:"
  du -sh /var/backups/wal_archive
'

log "Phase 2A completed. No restore operation was performed."
