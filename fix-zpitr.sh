#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${HOME}/zcoder"
PG_SERVICE="zpostgressql"
PITR_SERVICE="zpitr"
PITR_CONTAINER="zPITR"
PG_USER="zcoder"
PG_DATABASE="zcoder_db"
NETWORK="zPostgreSQL_network"
HBA_FILE="/var/lib/postgresql/data/pg_hba.conf"

log()  { printf '\n[%s] %s\n' "$(date '+%F %T')" "$*"; }
fail() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

cd "$PROJECT_DIR" || fail "Project directory not found: $PROJECT_DIR"

command -v docker >/dev/null || fail "Docker is required."
docker compose version >/dev/null 2>&1 || fail "Docker Compose is unavailable."

exec 9>/tmp/zcoder-zpitr-fix.lock
flock -n 9 || fail "Another zPITR repair is already running."

log "Checking required containers"
docker compose -f docker-compose.yml ps >/dev/null
docker compose -f docker-compose.zpitr.yml ps >/dev/null

docker inspect "$PG_SERVICE" >/dev/null 2>&1 ||
  fail "PostgreSQL container $PG_SERVICE does not exist."

docker inspect "$PITR_CONTAINER" >/dev/null 2>&1 ||
  fail "zPITR container $PITR_CONTAINER does not exist."

log "Discovering PostgreSQL Docker network subnet"
SUBNET="$(
  docker network inspect "$NETWORK" \
    --format '{{(index .IPAM.Config 0).Subnet}}'
)"

[[ "$SUBNET" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]] ||
  fail "Invalid or missing Docker subnet: $SUBNET"

RULE="host replication ${PG_USER} ${SUBNET} scram-sha-256"
log "Required HBA rule: $RULE"

log "Checking PostgreSQL replication role"
ROLE_OK="$(
  docker compose exec -T "$PG_SERVICE" \
    psql -X -U "$PG_USER" -d "$PG_DATABASE" -Atqc \
    "SELECT rolcanlogin AND rolreplication
       FROM pg_roles WHERE rolname = '${PG_USER}';"
)"

[[ "$ROLE_OK" == "t" ]] ||
  fail "Role $PG_USER must have LOGIN and REPLICATION privileges."

log "Backing up and ensuring pg_hba.conf rule"
docker compose exec -T "$PG_SERVICE" sh -lc '
  set -eu
  file="$1"
  rule="$2"

  test -f "$file"
  cp -p "$file" "${file}.backup.$(date +%Y%m%d%H%M%S)"

  if ! grep -Fqx "$rule" "$file"; then
    printf "\n%s\n" "$rule" >> "$file"
  fi
' sh "$HBA_FILE" "$RULE"

log "Reloading PostgreSQL configuration"
docker compose exec -T "$PG_SERVICE" \
  psql -X -U "$PG_USER" -d "$PG_DATABASE" -v ON_ERROR_STOP=1 \
  -c "SELECT pg_reload_conf();"

log "Validating HBA configuration"
HBA_ERRORS="$(
  docker compose exec -T "$PG_SERVICE" \
    psql -X -U "$PG_USER" -d "$PG_DATABASE" -Atqc \
    "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL;"
)"

[[ "$HBA_ERRORS" == "0" ]] ||
  fail "PostgreSQL reports $HBA_ERRORS pg_hba.conf parsing errors."

log "Validating mounted PostgreSQL secret"
docker compose -f docker-compose.zpitr.yml exec -T "$PITR_SERVICE" \
  sh -lc '
    set -eu
    password_file="${PGPASSWORD_FILE:-/run/secrets/zcoder_postgres_password}"
    test -r "$password_file"
    export PGPASSWORD
    PGPASSWORD="$(cat "$password_file")"
    psql -X -w -v ON_ERROR_STOP=1 \
      -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
      -Atqc "SELECT current_user || chr(64) || current_database();"
  ' || fail "PostgreSQL credentials validation failed."

log "Checking active WAL receiver connection"
is_streaming() {
  local result
  result="$(
    docker compose exec -T "$PG_SERVICE" \
      psql -X -U "$PG_USER" -d "$PG_DATABASE" -Atqc \
      "SELECT count(*)
         FROM pg_stat_activity
        WHERE backend_type = 'walsender'
          AND usename = '${PG_USER}'
          AND application_name = 'pg_receivewal'
          AND state = 'active';"
  )" || return 1

  [[ "$result" =~ ^[1-9][0-9]*$ ]]
}

if ! is_streaming; then
  log "WAL streaming is not active; restarting only zPITR"
  docker compose -f docker-compose.zpitr.yml \
    restart "$PITR_SERVICE"

  log "Waiting up to 60 seconds for WAL streaming"
  streaming=false

  for _ in $(seq 1 30); do
    sleep 2
    if is_streaming; then
      streaming=true
      break
    fi
  done

  [[ "$streaming" == true ]] || {
    docker logs --tail=80 "$PITR_CONTAINER" >&2
    fail "WAL streaming did not become active."
  }
else
  log "WAL streaming is already active; no restart required"
fi

log "Final PostgreSQL replication status"
docker compose exec -T "$PG_SERVICE" \
  psql -X -U "$PG_USER" -d "$PG_DATABASE" -c "
    SELECT pid, usename, application_name, client_addr,
           backend_type, state
      FROM pg_stat_activity
     WHERE backend_type = 'walsender';
  "

log "Recent zPITR logs"
docker logs --tail=20 "$PITR_CONTAINER" 2>&1

log "SUCCESS: PostgreSQL HBA, credentials and WAL streaming verified."
