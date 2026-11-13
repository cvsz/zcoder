#!/usr/bin/env bash
#
# docker-resource-audit.sh — ZCoder Docker & WSL2 Resource Audit
#
# Read-only diagnostics for the ZCoder Docker Compose stack and host
# container resources. Inspects containers, images, volumes, networks and
# the WSL2/host environment without starting, stopping, rebuilding or
# modifying anything.
#
# Usage:
#   docker-resource-audit.sh
#   DOCKER_COMPOSE_FILE=docker-compose.yml COMPOSE_PROJECT_NAME=zcoder \
#       docker-resource-audit.sh
#
# Exit status:
#   0  All expected resources are present and healthy (or not applicable).
#   1  Docker/compose is unavailable, the daemon is unreachable, or an
#      expected container/image/volume is missing or unhealthy.

set -Eeuo pipefail

ROOT_DIR="$(unset CDPATH; cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1

COMPOSE_FILE="${DOCKER_COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-zcoder}"

# Resources declared by docker-compose.yml that this audit expects to exist.
EXPECTED_CONTAINERS=(zpostgressql zredis zcoder-llm zcoder)
EXPECTED_IMAGES=("postgres:15-alpine" "redis:7-alpine" "zcoder:latest" "ghcr.io/ggml-org/llama.cpp:server")
EXPECTED_VOLUMES=(zpostgressql_data zredis_data zcoder-home)
EXPECTED_NETWORKS=(zPostgreSQL_network)

LLAMA_HEALTH_URL="http://127.0.0.1:8080/health"

# Host-side secret files referenced by docker-compose.yml. Existence and
# readability are checked; contents are never printed.
POSTGRES_SECRET_FILE="${ZCODER_POSTGRES_SECRET_SOURCE:-${HOME}/.config/zcoder/postgresql.password}"
REDIS_SECRET_FILE="${REDIS_SECRET_FILE:-/home/cvsz/.config/zcoder/redis.password}"

AUDIT_FAILED=0
AUDIT_CHECKS=0
AUDIT_WARNINGS=0

ok()    { printf '  [ok]    %s\n' "$*"; }
warn()  { printf '  [warn]   %s\n' "$*"; AUDIT_WARNINGS=$((AUDIT_WARNINGS + 1)); }
info()  { printf '  [info]   %s\n' "$*"; }
fail()  { printf '  [FAIL]   %s\n' "$*" >&2; AUDIT_FAILED=1; AUDIT_CHECKS=$((AUDIT_CHECKS + 1)); }
check() { AUDIT_CHECKS=$((AUDIT_CHECKS + 1)); }

section() {
    printf '\n=== %s ===\n' "$*"
}

# Run a read-only command, capturing its output without aborting on failure.
# Output is available in AUDIT_LAST_OUTPUT; exit status in AUDIT_LAST_RC.
capture() {
    local out
    AUDIT_LAST_OUTPUT=""
    AUDIT_LAST_RC=0
    out="$( "$@" 2>&1 )" || AUDIT_LAST_RC=$?
    AUDIT_LAST_OUTPUT="$out"
    return 0
}

have() {
    command -v "$1" >/dev/null 2>&1
}

# ── 0. Prerequisites ──────────────────────────────────────────────────────

section "Prerequisites"

if ! have docker; then
    fail "docker CLI is not installed"
    printf '\nSUMMARY: %d check(s), %d warning(s), %d failure(s)\n' \
        "$AUDIT_CHECKS" "$AUDIT_WARNINGS" "$AUDIT_FAILED"
    exit 1
fi
ok "docker CLI: $(docker version --format '{{.Client.Version}}' 2>/dev/null || true)"

capture docker compose version
if ((AUDIT_LAST_RC == 0)); then
    ok "Docker Compose: ${AUDIT_LAST_OUTPUT%%$'\n'*}"
else
    if have docker-compose; then
        warn "docker compose plugin unavailable; standalone docker-compose found"
    else
        fail "Docker Compose is not available (plugin or standalone)"
    fi
fi

capture docker info >/dev/null 2>&1
if ((AUDIT_LAST_RC != 0)); then
    fail "Docker daemon is unreachable (docker info failed)"
    printf '\nSUMMARY: %d check(s), %d warning(s), %d failure(s)\n' \
        "$AUDIT_CHECKS" "$AUDIT_WARNINGS" "$AUDIT_FAILED"
    exit 1
fi
ok "Docker daemon reachable"

# ── 1. Host & WSL2 environment ────────────────────────────────────────────

section "Host & WSL2 environment"

info "OS: $(uname -srm)"
if grep -qi microsoft /proc/version 2>/dev/null; then
    ok "WSL2 kernel detected"
else
    warn "WSL2 kernel not detected in /proc/version"
fi

if have wsl.exe; then
    capture wsl.exe --list --running 2>/dev/null
    if ((AUDIT_LAST_RC == 0)) && [[ -n "$AUDIT_LAST_OUTPUT" ]]; then
        info "Running WSL distros: ${AUDIT_LAST_OUTPUT//$'\n'/; }"
    else
        warn "wsl.exe present but no running distros reported"
    fi
else
    warn "wsl.exe not found (not running under WSL?)"
fi

info "CPUs: $(nproc 2>/dev/null || true)"
if [[ -r /proc/meminfo ]]; then
    local_mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    info "Memory: $((local_mem_kb / 1024)) MiB total"
else
    warn "Cannot read /proc/meminfo"
fi

capture df -h / 2>/dev/null
if ((AUDIT_LAST_RC == 0)); then
    info "Root filesystem: ${AUDIT_LAST_OUTPUT##*$'\n'}"
else
    warn "Cannot inspect root filesystem usage"
fi

# ── 2. Docker daemon ──────────────────────────────────────────────────────

section "Docker daemon"

capture docker info --format \
    'Server={{.ServerVersion}}\nStorageDriver={{.Driver}}\nRootDir={{.DockerRootDir}}\nCgroupDriver={{.CgroupDriver}}\nLoggingDriver={{.LoggingDriver}}'
if ((AUDIT_LAST_RC == 0)); then
    printf '%s\n' "$AUDIT_LAST_OUTPUT" | while IFS= read -r line; do
        [[ -n "$line" ]] && info "$line"
    done
else
    warn "docker info introspection failed"
fi

capture docker system df
if ((AUDIT_LAST_RC == 0)); then
    printf '%s\n' "$AUDIT_LAST_OUTPUT" | while IFS= read -r line; do
        [[ -n "$line" ]] && info "df: $line"
    done
else
    warn "docker system df failed"
fi

# ── 3. Compose project ────────────────────────────────────────────────────

section "Compose project ($COMPOSE_FILE)"

if [[ ! -f "$COMPOSE_FILE" ]]; then
    fail "Compose file not found: $COMPOSE_FILE"
else
    ok "Compose file present: $COMPOSE_FILE"
fi

COMPOSE=()
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif have docker-compose; then
    COMPOSE=(docker-compose -f "$COMPOSE_FILE")
fi

if (( ${#COMPOSE[@]} == 0 )); then
    warn "No Docker Compose implementation available; skipping compose checks"
else
    capture "${COMPOSE[@]}" config --quiet
    if ((AUDIT_LAST_RC == 0)); then
        ok "Compose configuration is valid"
    else
        fail "Compose configuration is invalid: ${AUDIT_LAST_OUTPUT}"
    fi

    capture "${COMPOSE[@]}" config --services
    if ((AUDIT_LAST_RC == 0)) && [[ -n "$AUDIT_LAST_OUTPUT" ]]; then
        info "Declared services: $(printf '%s' "$AUDIT_LAST_OUTPUT" | tr '\n' ',' | sed 's/,$//')"
    else
        warn "Could not enumerate compose services"
    fi
fi

# ── 4. Containers ─────────────────────────────────────────────────────────

section "Containers"

INSPECT_FMT='{{.State.Status}}|{{.State.Health.Status}}|{{.RestartCount}}|{{.Config.Image}}|{{.State.StartedAt}}|{{.HostConfig.NetworkMode}}|{{.NetworkSettings.Ports}}'

for name in "${EXPECTED_CONTAINERS[@]}"; do
    check
    capture docker inspect --type=container --format="$INSPECT_FMT" "$name"
    if ((AUDIT_LAST_RC != 0)); then
        fail "$name: container not found"
        continue
    fi

    IFS='|' read -r status health restarts image started_at netmode ports <<<"$AUDIT_LAST_OUTPUT"
    [[ -z "$health" ]] && health="<no healthcheck>"
    [[ -z "$ports" ]] && ports="<none published>"
    [[ -z "$netmode" ]] && netmode="default"

    case "$status" in
        running)
            case "$health" in
                healthy|"<no healthcheck>") ok "$name: running ($image, net=$netmode, restarts=$restarts, ports=$ports)" ;;
                *) warn "$name: running but health=$health (image=$image, net=$netmode)" ;;
            esac
            ;;
        *)
            warn "$name: $status (image=$image, net=$netmode, restarts=$restarts, started=$started_at)"
            ;;
    esac
done

# ── 5. Images ─────────────────────────────────────────────────────────────

section "Images"

capture docker images --format '{{.Repository}}:{{.Tag}}'
if ((AUDIT_LAST_RC == 0)); then
    installed_images="$(printf '%s\n' "$AUDIT_LAST_OUTPUT")"
else
    installed_images=""
    warn "docker images failed"
fi

for image in "${EXPECTED_IMAGES[@]}"; do
    check
    if printf '%s\n' "$installed_images" | grep -Fxq -- "$image"; then
        ok "Image present: $image"
    else
        fail "Image missing: $image"
    fi
done

if [[ -n "$installed_images" ]]; then
    dangling="$(printf '%s\n' "$installed_images" | grep -c '<none>:<none>' || true)"
    info "Dangling images: $dangling"
fi

# ── 6. Volumes ────────────────────────────────────────────────────────────

section "Volumes"

capture docker volume ls --format '{{.Name}}'
if ((AUDIT_LAST_RC == 0)); then
    volume_names="$(printf '%s\n' "$AUDIT_LAST_OUTPUT")"
else
    volume_names=""
    warn "docker volume ls failed"
fi

capture docker system df -v 2>/dev/null
if ((AUDIT_LAST_RC == 0)); then
    df_volumes="$AUDIT_LAST_OUTPUT"
else
    df_volumes=""
fi

for vol in "${EXPECTED_VOLUMES[@]}"; do
    check
    candidates=("$vol" "${COMPOSE_PROJECT_NAME}_${vol}")
    found=""
    for cand in "${candidates[@]}"; do
        if printf '%s\n' "$volume_names" | grep -Fxq -- "$cand"; then
            found="$cand"
            break
        fi
    done

    if [[ -z "$found" ]]; then
        fail "Volume not found: $vol (also tried ${COMPOSE_PROJECT_NAME}_$vol)"
        continue
    fi

    mountpoint="$(docker volume inspect --format '{{.Mountpoint}}' "$found" 2>/dev/null || true)"
    size=""
    if [[ -n "$df_volumes" ]]; then
        size="$(printf '%s\n' "$df_volumes" | awk -v name="$found" '$1 == name {print $3; exit}')"
    fi
    detail="mountpoint=$mountpoint"
    [[ -n "$size" ]] && detail="$detail, size=$size"
    ok "Volume present: $found ($detail)"
done

# ── 7. Networks ───────────────────────────────────────────────────────────

section "Networks"

capture docker network ls --format '{{.Name}}'
if ((AUDIT_LAST_RC == 0)); then
    network_names="$(printf '%s\n' "$AUDIT_LAST_OUTPUT")"
else
    network_names=""
    warn "docker network ls failed"
fi

for net in "${EXPECTED_NETWORKS[@]}"; do
    check
    if printf '%s\n' "$network_names" | grep -Fxq -- "$net"; then
        capture docker network inspect --format \
            'Driver={{.Driver}} Scope={{.Scope}}' "$net" 2>/dev/null || true
        detail="${AUDIT_LAST_OUTPUT:-}"
        ok "Network present: $net ${detail:+($detail)}"
    else
        fail "Network not found: $net"
    fi
done

# ── 8. Host secret files ──────────────────────────────────────────────────

section "Host secret files"

check_postgres() {
    check
    if [[ -f "$POSTGRES_SECRET_FILE" && -r "$POSTGRES_SECRET_FILE" && -s "$POSTGRES_SECRET_FILE" ]]; then
        ok "PostgreSQL secret file present and readable: $POSTGRES_SECRET_FILE"
    elif [[ -e "$POSTGRES_SECRET_FILE" ]]; then
        warn "PostgreSQL secret file exists but is empty or unreadable: $POSTGRES_SECRET_FILE"
    else
        warn "PostgreSQL secret file not found: $POSTGRES_SECRET_FILE"
    fi
}

check_redis() {
    check
    if [[ -f "$REDIS_SECRET_FILE" && -r "$REDIS_SECRET_FILE" && -s "$REDIS_SECRET_FILE" ]]; then
        ok "Redis secret file present and readable: $REDIS_SECRET_FILE"
    elif [[ -e "$REDIS_SECRET_FILE" ]]; then
        warn "Redis secret file exists but is empty or unreadable: $REDIS_SECRET_FILE"
    else
        warn "Redis secret file not found: $REDIS_SECRET_FILE"
    fi
}

check_postgres
check_redis

# ── 9. Local inference endpoint ───────────────────────────────────────────

section "Local inference endpoint ($LLAMA_HEALTH_URL)"

if have curl; then
    capture curl -fsS --max-time 5 "$LLAMA_HEALTH_URL"
    if ((AUDIT_LAST_RC == 0)); then
        ok "llama.cpp health endpoint responded: ${AUDIT_LAST_OUTPUT}"
    else
        warn "llama.cpp health endpoint unreachable (curl exit=$AUDIT_LAST_RC)"
    fi
else
    warn "curl not installed; skipping inference endpoint check"
fi

# ── Summary ───────────────────────────────────────────────────────────────

printf '\n=== Summary ===\n'
printf 'Checks : %d\nWarnings: %d\nFailures: %d\n' \
    "$AUDIT_CHECKS" "$AUDIT_WARNINGS" "$AUDIT_FAILED"

if ((AUDIT_FAILED != 0)); then
    exit 1
fi
exit 0
