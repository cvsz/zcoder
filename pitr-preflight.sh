#!/usr/bin/env bash
set -Eeuo pipefail

cd "$HOME/zcoder"

echo "=================================================="
echo " ZCODER PITR — PHASE 2 PREFLIGHT"
echo "=================================================="

echo
echo "===== 1. EXISTING BACKUP SCRIPT ====="
docker compose -f docker-compose.zpitr.yml exec -T zpitr \
  sh -lc 'sed -n "1,260p" /app/scripts/run_basebackup.sh'

echo
echo "===== 2. EXISTING RESTORE DRILL SCRIPT ====="
docker compose -f docker-compose.zpitr.yml exec -T zpitr \
  sh -lc 'sed -n "1,320p" /app/scripts/run_restore_drill.sh'

echo
echo "===== 3. BACKUP AND WAL DIRECTORY CONTENTS ====="
docker compose -f docker-compose.zpitr.yml exec -T zpitr \
  sh -lc '
    echo "--- Base backups ---"
    find /var/backups/base_backups -maxdepth 2 -type f \
      -printf "%TY-%Tm-%Td %TH:%TM:%TS %s %p\n" 2>/dev/null | sort

    echo "--- WAL archive ---"
    find /var/backups/wal_archive -maxdepth 2 -type f \
      -printf "%TY-%Tm-%Td %TH:%TM:%TS %s %p\n" 2>/dev/null | sort | tail -40

    echo "--- Disk usage ---"
    df -h /var/backups
    du -sh /var/backups/base_backups /var/backups/wal_archive
  '

echo
echo "===== 4. POSTGRESQL RECOVERY CONFIGURATION ====="
docker compose exec -T zpostgressql \
  psql -X -U zcoder -d zcoder_db -c "
    SELECT name, setting
    FROM pg_settings
    WHERE name IN (
      'wal_level',
      'archive_mode',
      'archive_command',
      'max_wal_senders',
      'wal_keep_size'
    )
    ORDER BY name;
  "

echo
echo "===== 5. REPLICATION STATUS ====="
docker compose exec -T zpostgressql \
  psql -X -U zcoder -d zcoder_db -c "
    SELECT pid, application_name, client_addr, state,
           sent_lsn, write_lsn, flush_lsn
    FROM pg_stat_replication;
  "

echo
echo "===== 6. COMPOSE VOLUMES ====="
docker volume ls --format '{{.Name}}' | grep -E 'zpitr|zcoder' || true

echo
echo "PREFLIGHT COMPLETE — NO BACKUP OR RESTORE OPERATIONS EXECUTED."
