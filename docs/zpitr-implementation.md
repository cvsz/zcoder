# zPITR — Point-in-Time Recovery Implementation

**zPITR** คือบริการ Docker สำหรับ Point-in-Time Recovery (PITR) ของ PostgreSQL อัตโนมัติ ใช้สำหรับสำรองข้อมูลต่อเนื่อง (WAL streaming), สำรองฐานข้อมูลทั้งก้อนเป็นระยะ (base backup), และซ้อมกู้คืน (restore drill) เพื่อออกหลักฐานประกอบ Release Gate

## สถานะ

มีอยู่จริงใน repository และควบคุมด้วย `docker-compose.zpitr.yml` กับโฟลเดอร์บริการ `deploy/docker/zpitr/`

## สถาปัตยกรรม

`zPITR` รันเป็น sidecar container บนเครือข่าย Docker `zPostgreSQL_network` ร่วมกับ `zpostgresql` (บริการ PostgreSQL เฉพาะของ ZCoder, ฐานข้อมูล `zcoder_db`, role `zcoder`) ประกอบด้วย:

- **`pg_receivewal` daemon** — สตรีม WAL อย่างต่อเนื่องจาก `zpostgresql` เข้า volume `zpitr_wal_archive` (RPO < 5 นาที)
- **`pg_basebackup` scheduler** — สำรองฐานข้อมูลทั้งก้อนเป็นระยะด้วย manifest SHA-256 เข้า volume `zpitr_base_backups`
- **Restore drill** — กู้คืนอย่างโดดเด่นใน isolated sandbox (`/tmp/pg_drill_data`) โดยใช้ `recovery.signal` + `restore_command` ตรวจสอบความต่อเนื่องของ WAL archive และออกหลักฐาน Release Gate

## การติดตั้งและรัน

```bash
# สร้างและเริ่ม zPITR (โหมด daemon สตรีม WAL ต่อเนื่อง)
docker compose -f docker-compose.zpitr.yml up -d --build

# ตรวจสอบการสตรีม WAL
docker logs -f zPITR
```

## รหัสผ่านและข้อมูลลับ (SEC-008)

รหัสผ่าน PostgreSQL ส่งผ่าน Docker secret (`zcoder_postgres_password`) แบบ mount read-only ที่ `/run/secrets/zcoder_postgres_password` ต้นทางฝั่ง host คือ `${HOME}/.config/zcoder/postgresql.password` (สิทธิ์ `0600`) เว้นแต่ `ZCODER_POSTGRES_SECRET_SOURCE` จะกำหนดเป็นอย่างอื่น **ห้ามฝังรหัสผ่านลงใน image หรือ `.env`**

## ซ้อมกู้คืนและหลักฐาน Release Gate

รัน drill กับ isolated target เพื่อสร้างหลักฐานที่ผูกกับ SHA ของ release candidate:

```bash
# รัน PITR drill (สร้างไฟล์ docs/evidence/pitr-qualification-<SHA>.json)
docker exec -it -e CANDIDATE_SHA="$(git rev-parse HEAD)" zPITR /app/scripts/run_restore_drill.sh

# ตรวจสอบไฟล์หลักฐาน
ls -la docs/evidence/pitr-qualification-*.json

# รัน Release Gate เพื่อยืนยันผล PASS
python scripts/release_gate.py --check
```

ไฟล์หลักฐาน JSON ยึดตามสキーマ v1 (`wal_archive_verified`, `restore_drill_passed`, `tested_at` เวลา UTC ชนิด Z, `evidence_sha256` 64-hex) ซึ่ง `scripts/release_gate.py` กำหนดให้ใช้

## คำสั่ง操作หลัก

| วัตถุประสงค์ | คำสั่ง |
|---|---|
| สตรีม WAL ต่อเนื่อง | `docker compose -f docker-compose.zpitr.yml up -d` |
| สำรองฐานข้อมูลด้วยตนเอง | `docker exec -it zPITR /app/scripts/run_basebackup.sh` |
| ซ้อมกู้คืน + สร้างหลักฐาน | `docker exec -it -e CANDIDATE_SHA=<SHA> zPITR /app/scripts/run_restore_drill.sh` |
| ดูไฟล์ใน WAL archive | `docker run --rm -v zpitr_wal_archive:/archive alpine ls -la /archive` |

## ข้อจำกัดสำคัญ

zPITR เป็นเครื่องมือซ้อมกู้คืน (DR rehearsal) และเครื่องมือ Release Gate การรับรอง PITR สำหรับสภาพจริงยังต้องอาศัยการกู้คืนโดยทีม Operations ต่อคลังข้อมูลจริงบน isolated target — การซ้อมในสภาพสังเคราะห์ในเครื่องไม่เพียงพอที่จะผ่านเกณฑ์การปล่อยระดับ production โดยลำพัง

## เอกสารที่เกี่ยวข้อง

- [`docs/operations/deployment.md`](docs/operations/deployment.md) § zPITR — การติดตั้ง, ตรวจสอบสุขภาพ, การ rollback ของ container
- [`docs/operations/dr-rehearsal.md`](docs/operations/dr-rehearsal.md) — รันบินซ้อมกู้คืนภัยพิบัติรายไตรมาส
- [`deploy/docker/zpitr/`](deploy/docker/zpitr/) — คำจำกัดความบริการ zPITR (Dockerfile, entrypoint, สคริปต์, Compose)
- [`scripts/release_gate.py`](scripts/release_gate.py) — ตรวจสอบเกณฑ์การปล่อยรวมถึงหลักฐาน PITR
