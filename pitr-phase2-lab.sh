#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

log() { printf '\n[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { echo "[FAIL] $*" >&2; exit 1; }

command -v docker >/dev/null || die "Docker CLI is required."
command -v date >/dev/null || die "date is required."
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable."

IMAGE="$(docker inspect zpostgressql --format '{{.Image}}')" ||
    die "Cannot resolve the existing PostgreSQL image."

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUFFIX="${STAMP}-$$"

NET="pitr-lab-net-${SUFFIX}"
PRIMARY="pitr-lab-primary-${SUFFIX}"
RECEIVER="pitr-lab-receiver-${SUFFIX}"
BACKUP_VOL="pitr-lab-backup-${SUFFIX}"
WAL_VOL="pitr-lab-wal-${SUFFIX}"
RECOVERY_VOL="pitr-lab-recovery-${SUFFIX}"
RECOVERY="pitr-lab-recovery-${SUFFIX}"

BACKUP_DIR="/backups/base_${STAMP}"
EVIDENCE="$PWD/pitr-phase2-evidence-${STAMP}.json"

LAB_PASSWORD="$(openssl rand -hex 24)" ||
    die "Cannot generate temporary lab password."

CREATED_NET=0
CREATED_VOLUMES=0
CREATED_PRIMARY=0
CREATED_RECEIVER=0

cleanup() {
    local rc=$?
    set +e

    if [ "$rc" -ne 0 ]; then
        echo
        echo "===== FAILURE DIAGNOSTICS ====="
        docker logs "$RECEIVER" 2>&1 | tail -80
        docker logs "$PRIMARY" 2>&1 | tail -80
    fi

    [ "$CREATED_RECEIVER" -eq 0 ] ||
        docker rm -f "$RECEIVER" >/dev/null 2>&1

    [ "$CREATED_PRIMARY" -eq 0 ] ||
        docker rm -f "$PRIMARY" >/dev/null 2>&1

    [ "$CREATED_NET" -eq 0 ] ||
        docker network rm "$NET" >/dev/null 2>&1

    if [ "$CREATED_VOLUMES" -ne 0 ]; then
        docker volume rm \
            "$BACKUP_VOL" "$WAL_VOL" "$RECOVERY_VOL" \
            >/dev/null 2>&1
    fi

    if [ "$rc" -eq 0 ]; then
        echo
        echo "Temporary PITR lab resources cleaned up."
        echo "Evidence: $EVIDENCE"
    else
        echo
        echo "PITR lab failed. Temporary resources were cleaned up."
        echo "Existing production and backup volumes were not touched."
    fi

    exit "$rc"
}
trap cleanup EXIT

log "Creating disposable PITR lab resources."

docker network create "$NET" >/dev/null
CREATED_NET=1

docker volume create "$BACKUP_VOL" >/dev/null
docker volume create "$WAL_VOL" >/dev/null
docker volume create "$RECOVERY_VOL" >/dev/null
CREATED_VOLUMES=1

docker run --rm \
    --volume "$BACKUP_VOL:/backups" \
    --volume "$WAL_VOL:/archive" \
    --volume "$RECOVERY_VOL:/recovery" \
    --entrypoint sh "$IMAGE" -c \
    'chown postgres:postgres /backups /archive /recovery'

log "Starting disposable PostgreSQL primary."

docker run -d \
    --name "$PRIMARY" \
    --network "$NET" \
    --network-alias pitr-primary \
    --env POSTGRES_USER=postgres \
    --env POSTGRES_PASSWORD="$LAB_PASSWORD" \
    --env POSTGRES_DB=pitr_lab \
    --volume "$BACKUP_VOL:/backups" \
    "$IMAGE" \
    postgres \
      -c wal_level=replica \
      -c max_wal_senders=8 \
      -c max_replication_slots=2 \
      -c listen_addresses='*' \
      -c wal_keep_size=128MB \
      >/dev/null

CREATED_PRIMARY=1

log "Waiting for disposable primary."

READY=0
for _ in $(seq 1 60); do
    if docker exec "$PRIMARY" pg_isready -U postgres -d pitr_lab \
        >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done

[ "$READY" -eq 1 ] || die "Disposable primary did not become ready."

SUBNET="$(docker network inspect "$NET" \
    --format '{{(index .IPAM.Config 0).Subnet}}')"

[[ "$SUBNET" =~ ^[0-9a-fA-F:.\/]+$ ]] ||
    die "Unexpected Docker network subnet."

docker exec "$PRIMARY" sh -c \
    'printf "host replication postgres %s scram-sha-256\n" "$1" >> "$PGDATA/pg_hba.conf"' \
    sh "$SUBNET"

docker exec "$PRIMARY" psql -U postgres -d postgres \
    -v ON_ERROR_STOP=1 \
    -c 'SELECT pg_reload_conf();' >/dev/null

log "Starting independent WAL receiver."

docker run -d \
    --name "$RECEIVER" \
    --network "$NET" \
    --env PGPASSWORD="$LAB_PASSWORD" \
    --volume "$WAL_VOL:/archive" \
    --entrypoint sh \
    "$IMAGE" -c \
    'exec gosu postgres pg_receivewal -h pitr-primary -p 5432 -U postgres -D /archive --verbose' \
    >/dev/null

CREATED_RECEIVER=1

log "Waiting for active WAL streaming."

STREAMING=0
for _ in $(seq 1 45); do
    COUNT="$(docker exec "$PRIMARY" \
        psql -U postgres -d postgres -Atqc \
        "SELECT count(*) FROM pg_stat_replication WHERE state = 'streaming';" \
        2>/dev/null || echo 0)"

    if [ "$COUNT" = "1" ]; then
        STREAMING=1
        break
    fi
    sleep 1
done

[ "$STREAMING" -eq 1 ] ||
    die "WAL receiver did not establish a streaming connection."

log "Creating an isolated base backup."

docker exec -u postgres "$PRIMARY" \
    mkdir -p "$BACKUP_DIR"

docker exec -u postgres \
    -e PGPASSWORD="$LAB_PASSWORD" \
    "$PRIMARY" \
    pg_basebackup \
      -h 127.0.0.1 \
      -p 5432 \
      -U postgres \
      -D "$BACKUP_DIR" \
      -Ft -z -Xs -P

docker exec "$PRIMARY" sh -c \
    'test -s "$1/base.tar.gz" &&
     test -s "$1/pg_wal.tar.gz" &&
     test -s "$1/backup_manifest"' \
    sh "$BACKUP_DIR" ||
    die "Base backup artifacts are incomplete."

docker exec "$PRIMARY" sh -c \
    'cd "$1" && sha256sum base.tar.gz > base.tar.gz.sha256' \
    sh "$BACKUP_DIR"

log "Creating recovery marker table and first transaction."

docker exec "$PRIMARY" psql -U postgres -d pitr_lab \
    -v ON_ERROR_STOP=1 \
    -c 'CREATE TABLE pitr_marker (
        id BIGSERIAL PRIMARY KEY,
        marker TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    );' >/dev/null

docker exec "$PRIMARY" psql -U postgres -d pitr_lab \
    -v ON_ERROR_STOP=1 \
    -c "INSERT INTO pitr_marker(marker) VALUES ('before_target');" \
    >/dev/null

log "Setting recovery target in the future."

TARGET_TIME="$(date -u -d '+4 seconds' '+%Y-%m-%d %H:%M:%S+00')"
echo "Recovery target UTC: $TARGET_TIME"

sleep 6

log "Creating second transaction after recovery target."

docker exec "$PRIMARY" psql -U postgres -d pitr_lab \
    -v ON_ERROR_STOP=1 \
    -c "INSERT INTO pitr_marker(marker) VALUES ('after_target');" \
    >/dev/null

log "Forcing WAL segment switch."

docker exec "$PRIMARY" psql -U postgres -d pitr_lab \
    -v ON_ERROR_STOP=1 \
    -c 'SELECT pg_switch_wal();'

sleep 5

log "Checking WAL archive contents."

WAL_COUNT="$(docker run --rm \
    --volume "$WAL_VOL:/archive:ro" \
    --entrypoint sh "$IMAGE" -c \
    'find /archive -maxdepth 1 -type f ! -name "*.partial" | wc -l')"

echo "Completed WAL files: $WAL_COUNT"

[ "$WAL_COUNT" -gt 0 ] ||
    die "No completed WAL segment found in archive."

log "Stopping WAL receiver cleanly."

docker stop -t 15 "$RECEIVER" >/dev/null
docker rm "$RECEIVER" >/dev/null
CREATED_RECEIVER=0

log "Starting isolated timestamp recovery."

docker run --rm \
    --name "$RECOVERY" \
    --network none \
    --volume "$BACKUP_VOL:/backups:ro" \
    --volume "$WAL_VOL:/archive:ro" \
    --volume "$RECOVERY_VOL:/recovery" \
    --env BACKUP_DIR="$BACKUP_DIR" \
    --env TARGET_TIME="$TARGET_TIME" \
    --entrypoint sh \
    "$IMAGE" -s <<'RECOVERY_SCRIPT'

set -eu

PGDATA=/recovery/data
LOG=/recovery/recovery.log

fail() {
    echo "[FAIL] $*" >&2
    [ ! -f "$LOG" ] || cat "$LOG" >&2
    exit 1
}

mkdir -p "$PGDATA" "$PGDATA/pg_wal"

echo "Extracting base backup."
tar -xzf "$BACKUP_DIR/base.tar.gz" -C "$PGDATA"
tar -xzf "$BACKUP_DIR/pg_wal.tar.gz" -C "$PGDATA/pg_wal"

cp "$BACKUP_DIR/backup_manifest" "$PGDATA/backup_manifest"

[ "$(cat "$PGDATA/PG_VERSION")" = "15" ] ||
    fail "Unexpected PostgreSQL version."

echo "Checking backup manifest."
pg_verifybackup --exit-on-error "$PGDATA" ||
    fail "Backup verification failed."

echo "Configuring timestamp recovery."

cat >> "$PGDATA/postgresql.auto.conf" <<EOF
restore_command = 'cp /archive/%f %p'
recovery_target_time = '$TARGET_TIME'
recovery_target_inclusive = 'on'
recovery_target_action = 'promote'
recovery_target_timeline = 'latest'
EOF

touch "$PGDATA/recovery.signal"

chown -R postgres:postgres /recovery
chmod 700 "$PGDATA"

[ "$(stat -c '%a' "$PGDATA")" = "700" ] ||
    fail "Invalid PostgreSQL data directory permissions."

echo "Starting PostgreSQL recovery."

gosu postgres postgres \
    -D "$PGDATA" \
    -c listen_addresses= \
    -c port=55433 \
    -c unix_socket_directories=/tmp \
    -c logging_collector=off \
    >"$LOG" 2>&1 &

PID=$!

cleanup_postgres() {
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
    fi
}
trap cleanup_postgres EXIT

READY=0

for _ in $(seq 1 90); do
    if ! kill -0 "$PID" 2>/dev/null; then
        fail "PostgreSQL exited during timestamp recovery."
    fi

    if pg_isready -h /tmp -p 55433 -U postgres -d pitr_lab \
        >/dev/null 2>&1; then
        READY=1
        break
    fi

    sleep 1
done

[ "$READY" -eq 1 ] ||
    fail "PostgreSQL did not become ready before timeout."

echo
echo "===== RECOVERY STATE ====="

STATE="$(psql -h /tmp -p 55433 -U postgres -d pitr_lab \
    -v ON_ERROR_STOP=1 -Atqc \
    'SELECT pg_is_in_recovery();')"

[ "$STATE" = "f" ] ||
    fail "Recovery did not complete and promote."

echo "PostgreSQL recovery state: complete"

echo
echo "===== MARKER VALIDATION ====="

COUNTS="$(psql -h /tmp -p 55433 -U postgres -d pitr_lab \
    -v ON_ERROR_STOP=1 -At -F '|' -c \
    "SELECT
       count(*) FILTER (WHERE marker = 'before_target'),
       count(*) FILTER (WHERE marker = 'after_target')
     FROM pitr_marker;")"

echo "before_target|after_target"
echo "$COUNTS"

[ "$COUNTS" = "1|0" ] ||
    fail "Timestamp recovery marker assertion failed."

echo
echo "===== RECOVERY LOG ====="
cat "$LOG"

echo
echo "TIMESTAMP PITR ASSERTIONS: PASSED"

RECOVERY_SCRIPT

log "Writing machine-readable evidence."

cat > "$EVIDENCE" <<EOF
{
  "test": "isolated-postgresql-timestamp-pitr",
  "status": "passed",
  "timestamp_utc": "$STAMP",
  "postgres_image": "$IMAGE",
  "backup_directory": "$BACKUP_DIR",
  "recovery_target_time_utc": "$TARGET_TIME",
  "assertions": {
    "base_backup_created": true,
    "wal_receiver_streaming": true,
    "wal_segment_archived": true,
    "postgresql_recovery_completed": true,
    "before_target_record_present": true,
    "after_target_record_absent": true,
    "production_database_modified": false,
    "production_backup_volumes_modified": false
  }
}
EOF

log "PHASE 2 TIMESTAMP PITR TEST PASSED."
echo "Evidence: $EVIDENCE"
