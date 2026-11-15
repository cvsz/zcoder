#!/usr/bin/env bash
# Auto-start ZCoder model server on WSL boot.
# Invoked by crontab @reboot for user cvsz.
set -euo pipefail

REPO_ROOT="/home/cvsz/zcoder"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/model-server-autostart.log"

mkdir -p "$LOG_DIR"

echo "[$(date -Iseconds)] Auto-starting ZCoder model servers..." >> "$LOG_FILE"

# Wait briefly for networking to be ready.
for i in $(seq 1 30); do
    if ping -c1 -W1 127.0.0.1 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

cd "$REPO_ROOT" || exit 1
"$REPO_ROOT/scripts/model-server" start all >> "$LOG_FILE" 2>&1

echo "[$(date -Iseconds)] Model server auto-start completed." >> "$LOG_FILE"
