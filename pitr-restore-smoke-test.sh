#!/usr/bin/env bash
#
# ZCODER PITR — ISOLATED RESTORE SMOKE TEST
# PostgreSQL 15
#
# Production safety:
# - Production PostgreSQL is never stopped or modified.
# - Backup and WAL volumes are mounted read-only.
# - Recovery container has no network access.
# - Recovery data is temporary.
# - Existing backups and WAL archives are preserved.
#
set -Eeuo pipefail
umask 077

PROJECT_DIR="${HOME}/zcoder"
BACKUP_VOLUME="zpitr_base_backups"
WAL_VOLUME="zpitr_wal_archive"
SOURCE_CONTAINER="zpostgressql"
LOCK_FILE="/tmp/zcoder-pitr-restore-smoke.lock"

TEST_CONTAINER=""

log() {
    printf '\n[%s] %s\n' "$(date -u +%FT%TZ)" "$*"
}

fail() {
    printf '\n[FAIL] %s\n' "$*" >&2
    exit 1
}

cleanup() {
    local status=$?

    if [[ -n "$TEST_CONTAINER" ]]; then
        docker rm -f "$TEST_CONTAINER" >/dev/null 2>&1 || true
    fi

    if [[ "$status" -eq 0 ]]; then
        log "Temporary recovery environment cleaned up."
    else
        printf '\n[FAIL] Restore test exited with status %s\n' "$status" >&2
    fi

    exit "$status"
}

trap cleanup EXIT

# --------------------------------------------------
# 1. HOST PREFLIGHT
# --------------------------------------------------

cd "$PROJECT_DIR" || fail "Project directory not found."

command -v docker >/dev/null 2>&1 ||
    fail "Docker is unavailable."

docker info >/dev/null 2>&1 ||
    fail "Docker daemon is unavailable."

docker inspect "$SOURCE_CONTAINER" >/dev/null 2>&1 ||
    fail "Production PostgreSQL container not found."

exec 9>"$LOCK_FILE"
flock -n 9 || fail "Another restore test is running."

# --------------------------------------------------
# 2. IDENTIFY IMAGE AND VOLUMES
# --------------------------------------------------

IMAGE_ID="$(
    docker inspect "$SOURCE_CONTAINER" --format '{{.Image}}'
)"

[[ "$IMAGE_ID" == sha256:* ]] ||
    fail "Cannot identify PostgreSQL image."

docker volume inspect "$BACKUP_VOLUME" >/dev/null ||
    fail "Backup volume not found: $BACKUP_VOLUME"

docker volume inspect "$WAL_VOLUME" >/dev/null ||
    fail "WAL volume not found: $WAL_VOLUME"

TEST_CONTAINER="zcoder-pitr-smoke-$(date -u +%Y%m%d%H%M%S)-$$"

log "PostgreSQL image: $IMAGE_ID"
log "Backup volume: $BACKUP_VOLUME"
log "WAL volume: $WAL_VOLUME"
log "Recovery container: $TEST_CONTAINER"

# --------------------------------------------------
# 3. RUN ISOLATED RECOVERY
#
# -i passes the following script through stdin.
# Quoted heredoc prevents host-shell expansion.
# --------------------------------------------------

docker run -i \
    --name "$TEST_CONTAINER" \
    --network none \
    --tmpfs /recovery:rw,size=1g,mode=0700 \
    --mount "type=volume,src=${BACKUP_VOLUME},dst=/backups,readonly" \
    --mount "type=volume,src=${WAL_VOLUME},dst=/wal,readonly" \
    --entrypoint sh \
    "$IMAGE_ID" -s <<'CONTAINER_SCRIPT'

set -eu

PGDATA="/recovery/data"
LOG="/tmp/pitr-recovery.log"
PID=""

fail() {
    echo "[FAIL] $*" >&2
    exit 1
}

cleanup_inner() {
    if [ -n "$PID" ]; then
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
    fi
}

trap cleanup_inner EXIT

# --------------------------------------------------
# 4. SELECT COMPLETE BACKUP
# --------------------------------------------------

echo
echo "===== SELECTING COMPLETE BACKUP ====="

BACKUP=""

for directory in /backups/base_*; do
    [ -d "$directory" ] || continue

    if [ -s "$directory/base.tar.gz" ] &&
       [ -s "$directory/pg_wal.tar.gz" ] &&
       [ -s "$directory/backup_manifest" ] &&
       [ -s "$directory/base.tar.gz.sha256" ]; then
        BACKUP="$directory"
    fi
done

[ -n "$BACKUP" ] ||
    fail "No complete base backup found."

echo "Selected backup: $BACKUP"

# --------------------------------------------------
# 5. CHECK REQUIRED BINARIES
# --------------------------------------------------

echo
echo "===== CHECKING POSTGRESQL BINARIES ====="

for cmd in \
    postgres \
    pg_isready \
    psql \
    pg_verifybackup \
    tar \
    gzip \
    sha256sum \
    gosu
do
    command -v "$cmd" >/dev/null 2>&1 ||
        fail "Missing required binary: $cmd"

    printf "%-20s %s\n" "$cmd" "$(command -v "$cmd")"
done

# --------------------------------------------------
# 6. VERIFY BASE CHECKSUM
#
# Read only the checksum value.
# Ignore the original absolute path stored in
# the checksum file.
# --------------------------------------------------

echo
echo "===== VERIFYING BASE SHA-256 ====="

CHECKSUM_FILE="$BACKUP/base.tar.gz.sha256"

IFS=' ' read -r EXPECTED _ < "$CHECKSUM_FILE"

ACTUAL_LINE="$(sha256sum "$BACKUP/base.tar.gz")"
ACTUAL="${ACTUAL_LINE%% *}"

[ -n "$EXPECTED" ] ||
    fail "Expected checksum is empty."

[ "$EXPECTED" = "$ACTUAL" ] ||
    fail "Base backup SHA-256 mismatch."

echo "Expected: $EXPECTED"
echo "Actual:   $ACTUAL"
echo "Base SHA-256: OK"

# --------------------------------------------------
# 7. VERIFY COMPRESSED ARCHIVES
# --------------------------------------------------

echo
echo "===== VERIFYING COMPRESSED ARCHIVES ====="

gzip -t "$BACKUP/base.tar.gz" ||
    fail "Base archive gzip verification failed."

gzip -t "$BACKUP/pg_wal.tar.gz" ||
    fail "WAL archive gzip verification failed."

echo "Base archive: OK"
echo "WAL archive: OK"

# --------------------------------------------------
# 8. VERIFY ARCHIVE STRUCTURE
# --------------------------------------------------

echo
echo "===== VERIFYING ARCHIVE STRUCTURE ====="

tar -tzf "$BACKUP/base.tar.gz" > /tmp/base-files.txt
tar -tzf "$BACKUP/pg_wal.tar.gz" > /tmp/wal-files.txt

grep -qx 'backup_label' /tmp/base-files.txt ||
    fail "backup_label missing."

[ -s "$BACKUP/backup_manifest" ] ||
    fail "Separate backup_manifest missing or empty."

echo "Separate backup manifest: OK"
echo "Base backup structure: OK"
echo "WAL archive structure: OK"

# --------------------------------------------------
# 9. EXTRACT BACKUP
# --------------------------------------------------

echo
echo "===== EXTRACTING BACKUP ====="

mkdir -p "$PGDATA/pg_wal"

tar -xzf "$BACKUP/base.tar.gz" -C "$PGDATA"
tar -xzf "$BACKUP/pg_wal.tar.gz" -C "$PGDATA/pg_wal"

# pg_basebackup -Ft stores backup_manifest separately.
cp "$BACKUP/backup_manifest" "$PGDATA/backup_manifest"

[ -s "$PGDATA/PG_VERSION" ] ||
    fail "PG_VERSION missing."

PG_VERSION="$(cat "$PGDATA/PG_VERSION")"

echo "PostgreSQL backup version: $PG_VERSION"

[ "$PG_VERSION" = "15" ] ||
    fail "Backup is not PostgreSQL 15."

[ -s "$PGDATA/backup_manifest" ] ||
    fail "Backup manifest missing after extraction."

# --------------------------------------------------
# 10. VERIFY BACKUP MANIFEST
# --------------------------------------------------

echo
echo "===== RUNNING PG_VERIFYBACKUP ====="

pg_verifybackup --exit-on-error "$PGDATA" ||
    fail "pg_verifybackup failed."

echo "pg_verifybackup: PASSED"

# --------------------------------------------------
# 11. PREPARE TEMPORARY POSTGRESQL
# --------------------------------------------------

echo
echo "===== PREPARING RECOVERY INSTANCE ====="

id postgres >/dev/null 2>&1 ||
    fail "PostgreSQL system user missing."

chown -R postgres:postgres /recovery
chmod 700 "$PGDATA"

echo "Recovery data directory permissions:"
stat -c '%a %U:%G %n' "$PGDATA"

[ "$(stat -c '%a' "$PGDATA")" = "700" ] ||
    fail "PostgreSQL data directory must have mode 0700."

[ "$(stat -c '%U:%G' "$PGDATA")" = "postgres:postgres" ] ||
    fail "PostgreSQL data directory ownership is incorrect."


# Command-line settings below override configuration
# inherited from the production backup.

# --------------------------------------------------
# 12. START ISOLATED POSTGRESQL
# --------------------------------------------------

echo
echo "===== STARTING POSTGRESQL ====="

gosu postgres postgres \
    -D "$PGDATA" \
    -c listen_addresses= \
    -c port=55433 \
    -c unix_socket_directories=/tmp \
    -c logging_collector=off \
    > "$LOG" 2>&1 &

PID=$!

echo "PostgreSQL PID: $PID"

# --------------------------------------------------
# 13. WAIT FOR STARTUP
# --------------------------------------------------

echo
echo "===== WAITING FOR POSTGRESQL ====="

READY="false"

for attempt in $(seq 1 60); do

    if pg_isready \
        -h /tmp \
        -p 55433 \
        -U zcoder \
        -d zcoder_db >/dev/null 2>&1; then

        READY="true"
        break
    fi

    if ! kill -0 "$PID" 2>/dev/null; then
        echo "PostgreSQL process exited."
        cat "$LOG"
        exit 1
    fi

    sleep 1
done

[ "$READY" = "true" ] || {
    echo "PostgreSQL startup timeout."
    cat "$LOG"
    exit 1
}

echo "PostgreSQL is accepting local connections."

# --------------------------------------------------
# 14. VERIFY DATABASE
# --------------------------------------------------

echo
echo "===== DATABASE VALIDATION ====="

psql -X \
    -h /tmp \
    -p 55433 \
    -U zcoder \
    -d zcoder_db \
    -v ON_ERROR_STOP=1 \
    -c "
        SELECT
            current_database() AS database,
            current_setting('server_version') AS version,
            pg_is_in_recovery() AS in_recovery;
    "

# --------------------------------------------------
# 15. DATABASE INVENTORY
# --------------------------------------------------

echo
echo "===== DATABASE INVENTORY ====="

psql -X \
    -h /tmp \
    -p 55433 \
    -U zcoder \
    -d zcoder_db \
    -v ON_ERROR_STOP=1 \
    -c "
        SELECT
            datname,
            pg_size_pretty(pg_database_size(datname)) AS size
        FROM pg_database
        ORDER BY datname;
    "

# --------------------------------------------------
# 16. ASSERT RECOVERY COMPLETE
# --------------------------------------------------

echo
echo "===== ASSERTING RECOVERY STATE ====="

IN_RECOVERY="$(
    psql -X \
        -h /tmp \
        -p 55433 \
        -U zcoder \
        -d zcoder_db \
        -Atqc "SELECT pg_is_in_recovery();"
)"

[ "$IN_RECOVERY" = "f" ] ||
    fail "PostgreSQL has not completed recovery."

echo "Recovery completed: YES"

# --------------------------------------------------
# 17. SQL READ TEST
# --------------------------------------------------

echo
echo "===== SQL READ TEST ====="

psql -X \
    -h /tmp \
    -p 55433 \
    -U zcoder \
    -d zcoder_db \
    -v ON_ERROR_STOP=1 \
    -c "
        SELECT
            now() AS recovery_test_time,
            current_user AS database_user,
            count(*) AS database_count
        FROM pg_database;
    "

# --------------------------------------------------
# 18. LOG OUTPUT
# --------------------------------------------------

echo
echo "===== RECOVERY SERVER LOG ====="

tail -40 "$LOG"

# --------------------------------------------------
# 19. SUCCESS
# --------------------------------------------------

echo
echo "=============================================="
echo " PITR BASE BACKUP SMOKE TEST: PASSED"
echo "=============================================="

echo "Verified:"
echo " - Base SHA-256"
echo " - Base archive integrity"
echo " - WAL archive integrity"
echo " - Backup manifest"
echo " - PostgreSQL 15 startup"
echo " - Database connectivity"
echo " - Recovery completion"
echo " - SQL read operation"

echo
echo "Production database was not modified."
echo "Backup and WAL volumes were read-only."
echo "PITR timestamp recovery remains unverified."

CONTAINER_SCRIPT

log "PASS: isolated base-backup recovery verified."

